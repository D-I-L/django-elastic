import json
import requests
import re
import logging
from search.elastic_settings import ElasticSettings
from builtins import classmethod

# Get an instance of a logger
logger = logging.getLogger(__name__)


class Elastic:
    ''' Elastic search '''

    def __init__(self, build_query=None, search_from=0, size=20, db=ElasticSettings.idx('DEFAULT')):
        ''' Query the elastic server for given search query '''
        self.url = (ElasticSettings.url() + '/' + db + '/_search?size=' + str(size) +
                    '&from='+str(search_from))
        if build_query is not None:
            if not isinstance(build_query, ElasticQuery):
                raise QueryError("not an ElasticQuery")
            self.query = build_query.query
        self.size = size
        self.db = db

    @classmethod
    def range_overlap_query(cls, seqid, start_range, end_range,
                            search_from=0, size=20, db=ElasticSettings.idx('DEFAULT'),
                            field_list=None):
        ''' Constructs a range overlap query '''
        query_bool = BoolQuery(must_arr=[{"range": {"start": {"lte": start_range}}},
                                         {"range": {"end": {"gte": end_range}}}])
        query_filter = Filter({"or": {"range": {"start": {"gte": start_range, "lte": end_range}}}})
        query_filter.extend("or", {"range": {"end": {"gte": start_range, "lte": end_range}}})
        query_filter.extend("or", query_bool.bool)
        query = ElasticQuery.filtered(Query.term({"seqid": seqid}), query_filter, field_list)
        return cls(query, search_from, size, db)

    @classmethod
    def field_search_query(cls, query_term, fields=None,
                           search_from=0, size=20, db=ElasticSettings.idx('DEFAULT')):
        ''' Constructs a field search query '''
        query = ElasticQuery.query_string(query_term, fields)
        return cls(query, search_from, size, db)

    def get_mapping(self, mapping_type=None):
        self.mapping_url = (ElasticSettings.url() + '/' + self.db + '/_mapping')
        if mapping_type is not None:
            self.mapping_url += '/'+mapping_type
        response = requests.get(self.mapping_url)
        if response.status_code != 200:
            return json.dumps({"error": response.status_code})
        return response.json()

    def get_count(self):
        ''' Return the elastic count for a query result '''
        url = ElasticSettings.url() + '/' + self.db + '/_count?'
        response = requests.post(url, data=json.dumps(self.query))
        return response.json()

    def get_json_response(self):
        ''' Return the elastic json response '''
        response = requests.post(self.url, data=json.dumps(self.query))
        logger.debug("curl '" + self.url + "&pretty' -d '" + json.dumps(self.query) + "'")
        if response.status_code != 200:
            logger.warn("Error: elastic response 200:" + self.url)
        return response.json()

    def get_result(self):
        ''' Return the elastic context result '''
        json_response = self.get_json_response()
        context = {"query": self.query}
        c_dbs = {}
        dbs = self.db.split(",")
        for this_db in dbs:
            stype = "Gene"
            if "snp" in this_db:
                stype = "Marker"
            if "region" in this_db:
                stype = "Region"
            c_dbs[this_db] = stype
        context["dbs"] = c_dbs
        context["db"] = self.db

        content = []
        if(len(json_response['hits']['hits']) >= 1):
            for hit in json_response['hits']['hits']:
                self._addInfo(content, hit)
                hit['_source']['idx_type'] = hit['_type']
                hit['_source']['idx_id'] = hit['_id']
                content.append(hit['_source'])
                # print(hit['_source'])

        context["data"] = content
        context["total"] = json_response['hits']['total']
        if(int(json_response['hits']['total']) < self.size):
            context["size"] = json_response['hits']['total']
        else:
            context["size"] = self.size
        return context

    def _addInfo(self, content, hit):
        ''' Parse VCF INFO field and add to the search hit '''
        if 'info' not in hit['_source']:
            return
        ''' Split and add INFO tags and values '''
        infos = re.split(';', hit['_source']['info'])
        for info in infos:
            if "=" in info:
                parts = re.split('=', info)
                if parts[0] not in hit['_source']:
                    hit['_source'][parts[0]] = parts[1]
            else:
                if info not in hit['_source']:
                    hit['_source'][info] = ""


class ElasticQuery:
    ''' Utility to assist in constructing Elastic queries. '''

    def __init__(self, query, sources=None):
        ''' Query the elastic server for given search query '''
        self.query = {"query": query}
        if sources is not None:
            self.query["_source"] = sources

    @classmethod
    def bool(cls, query_bool):
        if not isinstance(query_bool, BoolQuery):
            raise QueryError("not a BoolQuery")
        return cls(query_bool.bool)

    @classmethod
    def filtered_bool(cls, query_match, query_bool, sources=None):
        ''' '''
        if not isinstance(query_bool, BoolQuery):
            raise QueryError("not a BoolQuery")
        return ElasticQuery.filtered(query_match, Filter(query_bool.bool), sources)

    @classmethod
    def filtered(cls, query_match, query_filter, sources=None):
        ''' Builds a filtered query. '''
        if not isinstance(query_match, Query):
            raise QueryError("not a QueryMatch")
        if not isinstance(query_filter, Filter):
            raise QueryError("not a Filter")
        query = {"filtered": {"query": query_match.qmatch}}
        query["filtered"].update(query_filter.filter)
        return cls(query, sources)

    @classmethod
    def query_string(cls, query_term, fields=None, sources=None):
        ''' String query using a query parser in order to parse its content.
        Simple wildcards can be used with the fields supplied
        (e.g. "fields" : ["city.*"].) '''
        query = {"query_string": {"query": query_term}}
        if fields is not None:
            query["query_string"]["fields"] = fields
        return cls(query, sources)

    @classmethod
    def query_match(cls, match_id, match_str):
        ''' Basic match query '''
        query = {"match": {match_id: match_str}}
        return cls(query)


class Query:

    def __init__(self, qmatch):
        ''' Match query '''
        self.qmatch = qmatch

    @classmethod
    def match_all(cls):
        qmatch = {"match_all": {}}
        return cls(qmatch)

    @classmethod
    def term(cls, term):
        qmatch = {"term": term}
        return cls(qmatch)


class BoolQuery:

    def __init__(self, must_arr=None, must_not_arr=None, should_arr=None):
        ''' Bool query '''
        self.bool = {"bool": {}}
        if must_arr is not None:
            self.must(must_arr)
        if must_not_arr is not None:
            self.must_not(must_not_arr)
        if should_arr is not None:
            self.should(should_arr)

    def must(self, must_arr):
        self._update("must", must_arr)

    def must_not(self, must_not_arr):
        self._update("must_not", must_not_arr)

    def should(self, should_arr):
        self._update("should", should_arr)

    def _update(self, name, arr):
        if not isinstance(arr, list):
            arr = [arr]
        if name in self.bool["bool"]:
            self.bool["bool"][name].extend(arr)
        else:
            self.bool["bool"][name] = arr


class Filter:
    ''' http://www.elastic.co/guide/en/elasticsearch/reference/1.5/query-dsl-filters.html '''
    def __init__(self, qfilter):
        ''' Filter '''
        self.filter = {"filter": qfilter}

    def filter(self, qfilter):
        return self.filter

    def extend(self, filter_name, arr):
        if not isinstance(arr, list):
            arr = [arr]
        if filter_name in self.filter["filter"]:
            if not isinstance(self.filter["filter"][filter_name], list):
                self.filter["filter"][filter_name] = [self.filter["filter"][filter_name]]
            self.filter["filter"][filter_name].extend(arr)
        else:
            self.filter["filter"][filter_name] = arr


class QueryError(Exception):
    ''' GFF parse error  '''
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)
