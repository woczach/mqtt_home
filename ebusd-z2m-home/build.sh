#!/bin/bash
CONTAINERS="frontend backend"
version=0.3
for TARGET in $CONTAINERS; do
        docker image build --pull --tag parasolnikov/$TARGET:$version --target $TARGET .
        docker image push parasolnikov/$TARGET:$version
done