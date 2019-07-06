#!/usr/bin/env python
# coding: utf-8
#

from __future__ import print_function
import requests
import time
from datetime import datetime
import sys
import os
from collections import namedtuple
from functools import partial

if sys.version_info.major == 2:
    from ConfigParser import ConfigParser
    from urlparse import urljoin

elif sys.version_info.major == 3:
    from configparser import ConfigParser
    from urllib.parse import urljoin

QUERY_URL = "/api/v1/query"
headers = ['promql', 'winner',
           'ptype', 'pstatus', 'presult_count', 'ptime_duration',
           'ttype', 'tstatus', 'tresult_count', 'ttime_duration',
           'time']

ResultCsvFormat = namedtuple('ResultCsv', headers)


def join_url(server, url):
    if not server.startswith('http'):
        server = 'http://' + server

    return urljoin(server, url)


def get_config(path_to_cfg):
    if not os.path.isfile(path_to_cfg):
        raise ValueError("File [{}] not Exist!".format(path_to_cfg))

    PromThanosConfig = dict(count=1,
                            time_start=time.time())

    config = ConfigParser()
    config.read(path_to_cfg)

    PromThanosConfig['prometheus_server'] = join_url(
        config.get('server', 'prometheus_server'), QUERY_URL)
    PromThanosConfig['thanos_server'] = join_url(
        config.get('server', 'thanos_server'), QUERY_URL)
    PromThanosConfig['promql'] = config.get('promql', 'promql').split(',')

    if config.get('config', 'count'):
        PromThanosConfig['count'] = config.getint('config', 'count')

    if config.get('config', 'time_start'):
        time_start = config.get('config', 'time_start')
        dt = datetime.strptime(time_start, '%Y-%m-%d %H:%M:%S')
        PromThanosConfig['time_start'] = dt_to_ts(dt)

    if config.get('config', 'show_query_result'):
        PromThanosConfig['show_query_result'] = config.getint('config',
                                                              'show_query_result')

    return PromThanosConfig


def dt_to_ts(dt):
    # convert datetime to timestamp
    if sys.version_info.major == 3:
        return dt.timestamp()

    return time.mktime((dt.year, dt.month, dt.day,
                        dt.hour, dt.minute, dt.second,
                        -1, -1, -1))


def query(url, pql, time_start):
    params = dict(
        query=pql,
        dedup=True,
        partial_response=True,
        time=time_start
    )
    time_start = time.time()
    res = requests.get(url, params)
    time_duration = time.time() - time_start

    return res, time_duration


def query_all(prom_url, thanos_url, time_start, pql, show_query_result=False):
    prom_res, prom_time_duration = query(prom_url, pql, time_start)
    thanos_res, thanos_time_duration = query(thanos_url, pql, time_start)

    if show_query_result:
        print("=" * 10 + " Prometheus: {} ".format(pql) + "=" * 10)
        print(prom_res.request.url)
        print(prom_res.json())

        print("=" * 10 + " Thanos: {} ".format(pql) + "=" * 10)
        print(thanos_res.request.url)
        print(thanos_res.json())
        print('\n')

    return ResultCsvFormat._make(
        [
            pql,
            'prometheus' if prom_time_duration < thanos_time_duration else "thanos",

            'prom',
            prom_res.status_code,
            len(prom_res.json().get('data', dict()).get('result', list())),
            prom_time_duration,

            'thanos',
            thanos_res.status_code,
            len(thanos_res.json().get('data', dict()).get('result', list())),
            thanos_time_duration,

            datetime.now()
        ]
    )


if __name__ == "__main__":
    csv_file = os.path.join(os.path.curdir, 'result.csv')
    config_file = os.path.join(os.path.curdir, 'config.ini')

    PromThanosConfig = get_config(config_file)

    load_test_query = partial(query_all,
                              PromThanosConfig['prometheus_server'],
                              PromThanosConfig['thanos_server'],
                              PromThanosConfig['time_start'])

    data = list()
    thanos_win = 0
    thanos_error = 0

    prom_win = 0
    prom_error = 0

    for i in range(PromThanosConfig['count']):
        for pql in PromThanosConfig["promql"]:
            data.append(
                load_test_query(pql,
                                bool(PromThanosConfig['show_query_result']))
            )

    line_template = "| `{}` | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |"
    print("\n")
    print(line_template.format(*headers))
    print("| -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- |")

    for res in data:
        print(line_template.format(
            res.promql,
            res.winner,
            res.ptype,
            res.pstatus,
            res.presult_count,
            res.ptime_duration,
            res.ttype,
            res.tstatus,
            res.tresult_count,
            res.ttime_duration,
            res.time
        ))
        if res.winner == "thanos":
            thanos_win += 1
        else:
            prom_win += 1

        if res.tstatus >= 400:
            thanos_error += 1

        if res.pstatus >= 400:
            prom_error += 1

    data_len = len(data)

    print("\n\nresult: \n\tthanos win: {}\n\tthanos error: {}"
          "\n\tprometheus win: {}\n\tprometheus error: {}".format(
        thanos_win * 1.0 / data_len,
        thanos_error * 1.0 / data_len,
        prom_win * 1.0 / data_len,
        prom_error * 1.0 / data_len
    ))
