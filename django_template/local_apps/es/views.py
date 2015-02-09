from django.conf import settings
from django.shortcuts import render
import json
import requests
import re


def wildcard(request, query):
    query = query.replace("w", "*")
    data = {"query": {"wildcard": {"ID": query}}}
    context = _getContext(data)
    return render(request, 'search/elasticsearch.html', context)


def search(request, query):
    data = {"query": {"match": {"ID": query}}}
    context = _getContext(data)
    return render(request, 'search/elasticsearch.html', context,
                  content_type='text/html')


def _getContext(data):
    '''
    Query the elasticsearch server for given search data and return the
    context dictionary to pass to the template
    '''
    size = 20
    response = requests.post(settings.ELASTICSEARCH_URL +
                             '/dbsnp142/_search?size='+str(size),
                             data=json.dumps(data))

    context = {}
    content = []
    if(len(response.json()['hits']['hits']) >= 1):
        for hit in response.json()['hits']['hits']:
            #print(hit['_source']['REF']) @IgnorePep8
            _addInfo(content, hit)
            content.append(hit['_source'])
            #print(hit['_source']) @IgnorePep8

    context["data"] = content
    context["total"] = response.json()['hits']['total']
    if(int(response.json()['hits']['total']) < size):
        context["size"] = response.json()['hits']['total']
    else:
        context["size"] = size
    return context


def _addInfo(content, hit):
    '''
    Split and add INFO tags and values
    '''
    infos = re.split(';', hit['_source']['INFO'])
    for info in infos:
        if "=" in info:
            parts = re.split('=', info)
            if parts[0] not in hit['_source']:
                hit['_source'][parts[0]] = parts[1]
        else:
            if info not in hit['_source']:
                hit['_source'][info] = ""
