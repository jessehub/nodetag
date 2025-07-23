# nodetag

## What does it do?

Tag EKS nodes running in EC2 using annotations defined in the workloads scheduled to run on them

## Why would ya?

Billing and resource accounting is not simple in AWS and is even more opaque and complex once kubernetes is being used. Generally EKS nodes are meant to be shared resources where arbitrary workloads are scheduled. However there are cases where really there is only one primary business application being run on a given type of node. This is especially common when a pod requires the use of a single GPU, or one that is highly memory intensive. Another common use-case is a single-tenant service, where only one customer's compute is allowed to be resident on a node.

In this case it is useful to be able to tag an EKS node ec2 instance with the workload being run. The operator provided here looks for annotations in a Pod running on a Node. If the annotations match the unique prefix "nodetag/" then a tag will be applied to the node the pod is running on.

There is no attempt to avoid tag Name conflicts or to delete tags no longer associated with a running pod. When an appropriately prefixed tag Name is observed, then its Value is applied to the node. Plain and simple.

## How can I?

### Overview
1. Create IAM role for writing tags
2. Associate role with a service account in the cluster
3. Install operator and service account
4. Add annotations like `nodetag/<ec2 tag key>: <ec2 tag value>` to workload

The basic use case assumes that AWS pod identity is running. This allows the kubernetes service account associated with the operator can assume the IAM role needed for interacting with the AWS API. Once the basic role and policy are verified to be working they can be adjusted to be more restrictive to whatever degree is desired.

Edit the default `iam-role.json`, `pod-identity-trust.json` `iam-policy.json` files to suit your needs

### Specifics
1. Create IAM role and policy for writing tags
    ```
    CLUSTER_NAME=<the eks cluster name>
    ROLE_ARN=$(
     aws iam create-role \
        --role-name nodetag \
        --assume-role-policy-document file://pod-identity-trust.json \
        --query 'Role.Arn' \
        --output text
    )
    aws iam put-role-policy \
        --role-name nodetag --policy-name rwtags --policy-document file://iam-policy.json
    ```
2. Link the IAM role to the kubernetes Service Account the operator runs as
    ```
    aws eks create-pod-identity-association \
      --cluster-name $CLUSTER_NAME \
      --namespace nodetag \
      --service-account nodetag \
      --role-arn $ROLE_ARN
    ```
3. Install the operator in the nodetag namespace
   ```commandline
   helm install -n nodetag --create-namespace charts/nodetag
   ```

If you do not have the pod identity service then you can set it up eksctl

   *eg*
   ```
   eksctl create addon --name eks-pod-identity-agent --cluster $CLUSTER_NAME
   ```

## Security

This is a blunt tool and has the power to write arbitrary tags to your ec2 instances. To some parties this is a non-starter. However in many cases this should be perfectly acceptable, given that you are in control of the workload specs being scheduled on the cluster. There are a couple of places to put some guardrails in place by refining the service account and iam policy. Further restrictions can be coded into the operator since the code is simple to modify.

I had thought of making a feature for allowing/rejecting certain tag keys into the operator, possibly through a ConfigMap or CRD. However, it's just as easy to do this in the policy attached to the IAM role and why not use that more robust security feature since AWS already provides it.

## Customization

The source code is very simple to read, and it can be customized to whatever suits your purpose. I encourage you to follow good principles of operator design. I hope that I have followed these same tenets in the original code. Contributions are welcome. Bug reports are welcome.

 1. don't hold a lot of state in-process
 2. run quickly
 3. fail explicitly
