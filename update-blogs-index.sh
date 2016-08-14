#!/bin/bash

python2.7 elasticsearch-index.py -H localhost -P 9200 -i blogs -t article -cc _config.yml -f .es-last-index-time -e .es-exclude-articles
echo
