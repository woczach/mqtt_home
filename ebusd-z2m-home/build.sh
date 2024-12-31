#!/bin/bash
CONTAINERS="frontend controller watcher"
version=0.4
for TARGET in $CONTAINERS; do
        docker image build --pull --tag parasolnikov/$TARGET:$version --target $TARGET .
        docker image push parasolnikov/$TARGET:$version
done