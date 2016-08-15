# Hexo Elasticsearch 辅助脚本

### 安装依赖
```
sudo pip install elasticsearch PyYaml
```

### 文件说明

* blogs-index.txt: 定义 blogs 索引。
* create-blogs-index.sh: 读取 blogs-index.txt 文件并创建 blogs 索引。
* delete-blogs-index.sh: 删除 blogs 索引。
* update-blogs-index.sh: 使用 elasticsearch-index.py 脚本读取 hexo 的缓存文件 db.json，并重新索引更新过的文章。

## 需要注意的地方

* 这里默认 elasticsearch 服务运行在 localhost:9200。
* 建立索引的时候，使用了处理过的 page.path 作为 Document ID，因为 hexo 每次清缓存后 page.id 会改变。
* elasticsearch-index.py 脚本每次更新索引之后，都会把更新时间(东八区)记录下来(默认是.es-last-index-time)，下一次更新的时候，只会更新 page.updated 大于上次索引更新时间的文章。如果要重建索引，直接删除这个文件即可。
* 如果有不想建索引的文章，可以在 exclude 文件(默认是 .es-exclude-articles) 里列出文章的路径 (page.path)，例如：

    ```
    /search.html
    /404.html
    ````
