import kopf
import kubernetes
import logging
import re
import boto3

"""Tags are specified with user-specified workload annotations "nodetag/Name1": "Value1" for each tag name and value to apply"""
ANNOTATION_PREFIX = "nodetag/"

"""Annotations are kept on the node to memoize what has already been written to aws"""
NODE_TAG_APPLIED = "nodetag.applied/"

# TODO fix this:
# Absence of either namespaces or cluster-wide flag will become an error soon.
# For now, switching to the cluster-wide mode for backward compatibility.

def actionable_pod(spec, **kwargs):
    annotations = kwargs.get('annotations',{})
    tags = tags_from_annotations(annotations, ANNOTATION_PREFIX)
    node_name = kwargs.get('body', {}).get('spec',{}).get('nodeName')
    if not all([tags, node_name]):
        return False
    return True

@kopf.on.create("v1","pods", when=actionable_pod)
def pod_create_handler(body, **kopf_kwargs):
    pod_event(body, **kopf_kwargs)

def pod_event(pod_spec, **kopf_kwargs):
    annotations = pod_spec.get('metadata', {}).get('annotations', {})
    tags = tags_from_annotations(annotations, ANNOTATION_PREFIX)
    node_name = pod_spec.get('spec', {}).get('nodeName')
    logging.info("Pod has nodetag/ annotations", extra={"tags": tags, "node_name": node_name})
    node = node_from_name(node_name)
    apply_tags(tags, node)

def pod_node(spec):
    spec.get('spec', {}).get('nodeName')

def tags_from_annotations(annotations: dict, annotation_prefix: str):
    tags = {}
    for anno_key, anno_value in annotations.items():
        if not anno_key.startswith(annotation_prefix):
            continue
        tag_key = anno_key[len(annotation_prefix):]
        if not tag_key:
            logging.warning("Empty tag key for prefix", extra={"annotation_prefix": annotation_prefix})
            continue
        # it is ok for Value to be an empty string
        tags[tag_key] = anno_value
    return tags

def node_from_name(node_name: str) -> kubernetes.client.V1Node:
    try:
        api = kubernetes.client.CoreV1Api()
        node = api.read_node(name=node_name)
    except kubernetes.client.ApiException as e:
        raise kopf.TemporaryError(f"Failed to get Node {node_name}, retrying{e}", delay=10)
    return node

def node_aws_id_and_region(node) ->(str,str):
    provider_id = node.spec.provider_id
    if not provider_id:
        raise kopf.PermanentError("Node provider_id not found in spec")
    matches = re.match(r"aws:///(.+-.+.{1}).+/(i-.+)", provider_id)
    if not matches:
        raise kopf.PermanentError("Node provider_id does not match regex aws:///(.+-.+.{1}).+/(.+)")
    region = matches[1]
    instance_id = matches[2]
    return instance_id, region

def apply_tags(tags: dict, node: kubernetes.client.V1Node):
    node_annotations = node.metadata.annotations
    if not node_annotations:
        kopf.PermanentError("Node annotations not found")
    node_tags_applied = tags_from_annotations(node.metadata.annotations, NODE_TAG_APPLIED)
    new_tags = {k:v for k,v in tags.items() if not node_tags_applied.get(k) == v}
    applied_tags = {k:v for k,v in node_tags_applied.items() if tags.get(k) == v}
    logging.info({"desired_tags": tags, "new_tags": new_tags, "applied_tags": applied_tags})
    if not new_tags:
        logging.info("Node metadata denotes the desired tags have already been applied")
        return
    instance_id, region = node_aws_id_and_region(node)
    ec2 = boto3.client('ec2', region_name=region)
    tag_list = [{"Key":k, "Value": v} for k,v in new_tags.items()]
    response = ec2.create_tags(Resources=[instance_id],Tags=tag_list)
    aws_retries = response.get('ResponseMetatdata',{}).get("RetryAttempts",0)
    if aws_retries != 0:
        logging.error("AWS ec2 create_tags call was retried multiple times", extra={"response": response})
        pass
    logging.info("Tags were applied to ec2 node successfully")
    k8s = kubernetes.client.CoreV1Api()
    node_patch = {
        "metadata": {
            "annotations": {
            }
        }
    }
    for k,v in new_tags.items():
        node_patch["metadata"]["annotations"][f"{NODE_TAG_APPLIED}{k}"] = v
    try:
        k8s.patch_node(node.metadata.name, node_patch)
    except:
        raise kopf.TemporaryError("Could not update")
    logging.info("Applied tags were memoized in node annotations successfully")
