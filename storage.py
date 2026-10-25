# coding: utf-8
'''
存储后端

- `file` : 本地 `data.json` *(默认)*
- `upstash` : Upstash Redis (REST API) —— 用于 Vercel 等无状态 / 无持久磁盘环境

切换方式: 配置环境变量 (任一组合均可, 见 doc/env.md):

    UPSTASH_REDIS_REST_URL / UPSTASH_REDIS_REST_TOKEN
    KV_REST_API_URL        / KV_REST_API_TOKEN          (Vercel KV / Marketplace 集成自动注入)

只要 `url` 与 `token` 都有值, 就使用 Upstash, 否则回退到本地文件。
'''

import json
import os
from urllib import request as urlrequest

import utils as u


class StorageError(Exception):
    '''
    存储后端读写错误
    '''


class FileStorage:
    '''
    本地文件后端 *(行为与原 `data.json` 一致)*
    '''

    name = 'file'
    remote = False  # 是否为远端存储 (远端时读请求需要 refresh)

    def __init__(self, filename: str = 'data.json'):
        self.path = u.get_path(filename)

    def read(self) -> str | None:
        '''
        读取原始文本, 不存在时返回 `None`
        '''
        try:
            with open(self.path, 'r', encoding='utf-8') as file:
                return file.read()
        except FileNotFoundError:
            return None

    def write(self, text: str) -> None:
        '''
        写入原始文本 *(先写临时文件再替换, 避免写入中断导致文件损坏)*
        '''
        tmp_path = f'{self.path}.tmp'
        try:
            with open(tmp_path, 'w', encoding='utf-8') as file:
                file.write(text)
                file.flush()
                os.fsync(file.fileno())
            os.replace(tmp_path, self.path)
        except Exception as e:
            raise StorageError(f'write {self.path} failed: {e}')


class UpstashStorage:
    '''
    Upstash Redis 后端 *(通过 REST API, 不引入额外依赖)*

    使用单条命令的 REST 接口: `POST <url>` body 为 `["SET", key, value]` / `["GET", key]`
    '''

    name = 'upstash'
    remote = True

    def __init__(self, url: str, token: str, key: str = 'sleepy:data', timeout: int = 5):
        self.url = url.rstrip('/')
        self.token = token
        self.key = key
        self.timeout = timeout

    def _command(self, *args):
        '''
        执行一条 Redis 命令, 返回 `result` 字段
        '''
        body = json.dumps(list(args), ensure_ascii=False).encode('utf-8')
        req = urlrequest.Request(
            self.url,
            data=body,
            method='POST',
            headers={
                'Authorization': f'Bearer {self.token}',
                'Content-Type': 'application/json'
            }
        )
        try:
            with urlrequest.urlopen(req, timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            raise StorageError(f'upstash request failed: {e}')
        if isinstance(payload, dict) and payload.get('error'):
            raise StorageError(f'upstash error: {payload["error"]}')
        if isinstance(payload, dict):
            return payload.get('result')
        return payload

    def read(self) -> str | None:
        return self._command('GET', self.key)

    def write(self, text: str) -> None:
        res = self._command('SET', self.key, text)
        if res != 'OK':
            raise StorageError(f'upstash set returned {res!r}')


def _first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value.strip()
    return ''


def get_storage() -> FileStorage | UpstashStorage:
    '''
    按环境变量选择后端 *(见模块开头说明)*
    '''
    url = _first_env('UPSTASH_REDIS_REST_URL', 'KV_REST_API_URL')
    token = _first_env('UPSTASH_REDIS_REST_TOKEN', 'KV_REST_API_TOKEN')
    if url and token:
        key = _first_env('SLEEPY_REDIS_KEY') or 'sleepy:data'
        u.info(f'[storage] using upstash redis: {url} (key: {key})')
        return UpstashStorage(url=url, token=token, key=key)
    return FileStorage()
