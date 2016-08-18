#!/usr/bin/env python
# -*- coding: utf-8 -*-

# index posts in db.json with elasticsearch
# 2016.07.23 mawenbao
# depends on elasticsearch and PyYaml
#     pip install elasticsearch PyYaml

import re
import os
import yaml
import json
import argparse
from datetime import datetime
from elasticsearch import Elasticsearch
from elasticsearch import helpers as es_helpers
from elasticsearch.exceptions import AuthenticationException

date_format = '%Y-%m-%dT%H:%M:%S.%fZ'
epoch = datetime.fromtimestamp(0)
tag_stripper = re.compile(r'(<!--.*?-->|<[^>]*>)')

def parse_cmd_args():
    argParser = argparse.ArgumentParser(description=u'Index posts and pages in db.json with elasticsearch')
    argParser.add_argument('-c', dest='cache', default='db.json', help=u'path of hexo db.json')
    argParser.add_argument('-cc', dest='config', default='_config.yml', help=u'path of hexo configuration file')
    argParser.add_argument('-f', dest='lastIndexTimeFile', default='.es-last-index-time', help=u'path of the file which records the last index time')
    argParser.add_argument('-e', dest='excludeFile', default='.es-exclude-articles', help=u'list of article paths not to be indexed')
    argParser.add_argument('-H', dest='host', default='localhost', help=u'host of elasticsearch server')
    argParser.add_argument('-P', dest='port', default=9200, type=int, help=u'port of elasticsearch server')
    argParser.add_argument('-u', dest='user', default='', help=u'elasticsearch shield user name')
    argParser.add_argument('-p', dest='passwd', default='', help=u'elasticsearch shield user password')
    argParser.add_argument('-i', dest='index', required=True, help=u'elasticsearch index name')
    argParser.add_argument('-t', dest='doctype', required=True, help=u'elasticsearch type name')
    return argParser.parse_args()

def parse_local_datetime(time_str):
    dt = datetime.strptime(time_str, date_format)
    return int((dt - epoch).total_seconds());

def parse_datetime(time_str):
    dt = datetime.strptime(time_str, date_format)
    # 转换到东八区时间
    return int((dt - epoch).total_seconds()) + 8 * 3600;

def load_category_map(hexo_config):
    with open(hexo_config) as f:
        cat_map = yaml.load(f).get('category_map')
        if not cat_map:
            print('category_map not defined in hexo config %s' % hexo_config)
        return cat_map

def load_cats_tags(cache):
    cats = {}
    tags = {}
    for c in cache['models']['Category']:
        cats[c['_id']] = c['name']
    for t in cache['models']['Tag']:
        tags[t['_id']] = t['name']
    return cats, tags

# add categories and tags to articles
def analyze_cache(cache, articles):
    articles_map = { a['_id'] : a for a in articles }
    cats, tags = load_cats_tags(cache)

    def _set_meta(cache_index, metas, meta_index, meta_name):
        for r in cache['models'][cache_index]:
            art = articles_map.get(r['post_id'])
            if not art:
                continue
            meta = metas[r[meta_index]]
            if not meta_name in art:
                art[meta_name] = [meta]
            else:
                art[meta_name].append(meta)

    _set_meta('PostCategory', cats, 'category_id', 'categories')
    _set_meta('PostTag', tags, 'tag_id', 'tags')
    return articles_map

def load_valid_articles(cache, last_index_time):
    def will_index(article, is_post=True):
        updated = parse_datetime(article['updated'])
        if article.get('published') == 0 or updated < last_index_time:
            # no need to index
            return False
        return True

    articles = []
    for a in cache['models']['Post']:
        if will_index(a):
            print('Loaded post: %s' % a['title'])
            articles.append(a)
    for a in cache['models']['Page']:
        if will_index(a):
            print('Loaded page: %s' % a['title'])
            articles.append(a)
    print('\nLoaded %d articles' % len(articles))
    return analyze_cache(cache, articles)

def build_path(article, category_map):
    slug = article.get('slug')  # post
    path = article.get('path')  # page

    if path:
        return '/' + path

    # /category_1/category_2/slug.html
    art_path = ''
    for cat in article['categories']:
        cat_alias = category_map.get(cat)
        if cat_alias:
            art_path += '/' + cat_alias
        else:
            art_path += '/' + cat
    return art_path + '/' + slug + '.html'

def to_actions(articles, category_map, excludes, index, doctype):
    actions = []
    for a in articles:
        art_path = build_path(a, category_map)
        if art_path in excludes:
            print('- Article %s omitted' % a['title'])
            continue
        stripped_content = tag_stripper.sub('', a['content'])
        act = {
            '_index': index,
            '_type': doctype,
            '_op_type': 'index',
            '_id': art_path.strip('.html').strip('/').replace('/', '.'),
            '_source': {
                'title': a['title'],
                'date': parse_datetime(a['date']),
                'updated': parse_datetime(a['updated']),
                'content': stripped_content,
                'path': art_path,
                'excerpt': a['excerpt'] or '\n'.join(stripped_content.split('\n')[:2])
            }
        }
        act_source = act['_source']
        if 'categories' in a:
            act_source['categories'] = a['categories']
        if 'tags' in a:
            act_source['tags'] = a['tags']
        actions.append(act)
    return actions

def main():
    args = parse_cmd_args()
    if not os.path.exists(args.cache) or not os.path.isfile(args.cache):
        print('cache file %s not found' % args.cache)
        return -1
    if not os.path.exists(args.config) or not os.path.isfile(args.config):
        print('hexo config file %s not found' % args.config)
        return -1

    category_map = load_category_map(args.config)

    last_index_time = 0
    if os.path.exists(args.lastIndexTimeFile) and os.path.isfile(args.lastIndexTimeFile):
        with open(args.lastIndexTimeFile) as f:
            index_time_str = f.read().strip()
            try:
                last_index_time = parse_local_datetime(index_time_str)
            except Exception as e:
                print('Error loading last index time from %s: %s'
                      % (args.lastIndexTimeFile, e))
    excludePaths = {}
    if os.path.exists(args.excludeFile) and os.path.isfile(args.excludeFile):
        with open(args.excludeFile) as f:
            excludePaths = { k.strip(): True for k in f.readlines() }

    serverAddr = '%s:%d' % (args.host, args.port)
    if args.user and args.passwd:
        serverAddr = '%s:%s@%s' % (args.user, args.passwd, serverAddr)
    es_client = Elasticsearch([serverAddr], timeout=60)
    if not es_client.ping():
        print('failed to ping elasticsearch server at %s:%d' % (args.host, args.port))
        return -1

    with open(args.cache) as f:
        cache = json.load(f)
        articles_map = load_valid_articles(cache, last_index_time)
        actions = to_actions(articles_map.values(), category_map,
                             excludePaths, args.index, args.doctype)
        try:
            es_helpers.bulk(es_client, actions, refresh = True)
        except es_helpers.BulkIndexError as e:
            print('\n' + e.args[0] + ':')
            for err in e.errors:
                err = err['index']
                print('# ' + articles_map[err['_id']]['title']
                      + '> ' + err['error']['reason'] + ' ('
                      + err['error']['caused_by']['reason']) + ')'
            print('\n%d articles indexed successfully, %d failed.' %
                  (len(actions) - len(e.errors), len(e.errors)))
        else:
            print('\n%d articles indexed successfully.' % len(actions))

    # save index time
    with open(args.lastIndexTimeFile, 'w') as f:
        f.write(datetime.now().strftime(date_format))

if __name__ == '__main__':
    main()
