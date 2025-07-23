#!/bin/sh
set -e
set -x
echo This takes a minute to startup...
kopf run -m nodetag --verbose
