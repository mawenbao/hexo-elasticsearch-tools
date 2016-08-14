#!/bin/sh

curl -XPOST http://localhost:9200/blogs -d @blogs-index.txt
echo
