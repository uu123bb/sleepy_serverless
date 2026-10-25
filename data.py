# coding: utf-8

import copy
import os
import pytz
import json
import threading
from time import sleep
from datetime import datetime

import utils as u
import env as env
from setting import metrics_list
from storage import get_storage


class data:
    '''
    data 类，存储当前/设备状态
    可用 `.data['xxx']` 直接调取数据 (加载后) *(?)*
    '''
    data: dict
    preload_data: dict
    data_check_interval: int = 60

    def __init__(self):
        self.storage = get_storage()
        self.dirty = False  # 内存中是否有尚未写回存储的改动 (metrics 等)
        with open(u.get_path('data.template.json'), 'r', encoding='utf-8') as file:
            self.preload_data = json.load(file)
        try:
            if self.storage.read() is None:
                u.info(f'Could not find data in {self.storage.name}, creating.')
                self.data = copy.deepcopy(self.preload_data)
                self.save()
            else:
                self.load()
        except Exception as e:
            u.warning(f'Error when loading data: {e}, try re-create')
            self.data = copy.deepcopy(self.preload_data)
            self.save()
            try:
                self.load()
            except Exception as e2:
                # 存储后端不可用时降级为内存中的模板数据, 避免整个服务起不来
                u.error(f'Reload failed, serving template data in memory only: {e2}')

    # --- Storage functions

    def load(self, ret: bool = False, preload: dict = {}, error_count: int = None) -> dict:
        '''
        从存储后端加载状态

        :param ret: 是否返回加载后的 dict (为否则设置 self.data)
        :param preload: 将会将存储中的内容追加到此后
        :param error_count: 重试次数 (默认: 本地文件 5 次, 远端存储 2 次以免冷启动过慢)
        '''
        if not preload:
            preload = self.preload_data
        if error_count is None:
            error_count = 2 if self.storage.remote else 5
        attempts = error_count

        while attempts > 0:
            try:
                raw = self.storage.read()
                if raw is None:
                    u.warning(f'data not found in {self.storage.name}, try re-create')
                    DATA = copy.deepcopy(preload)
                    if ret:
                        return DATA
                    self.data = DATA
                    self.save()
                    return DATA if ret else None
                DATA: dict = {**preload, **json.loads(raw)}
                if ret:
                    return DATA
                self.data = DATA
                self.dirty = False
                if env.util.metrics:
                    self._ensure_metrics()  # 远端数据可能缺 metrics 字段
                break  # 成功加载数据后跳出循环
            except Exception as e:
                attempts -= 1
                if attempts > 0:
                    u.warning(f'Load data error: {e}, retrying ({attempts} attempts left)')
                else:
                    u.error(f'Load data error: {e}, reached max retry count!')
                    raise

    def save(self, raise_on_error: bool = False):
        '''
        将内存中的状态写回存储后端

        :param raise_on_error: 写入失败时是否抛出异常 (为否则仅记录日志)
        '''
        try:
            self.storage.write(json.dumps(self.data, indent=4, ensure_ascii=False))
            self.dirty = False
        except Exception as e:
            u.error(f'Failed to save data: {e}')
            if raise_on_error:
                raise

    def refresh(self):
        '''
        从存储后端重新读取最新状态

        仅在远端存储 (如 Upstash) 下生效 —— 服务端无状态部署时,
        不同实例各有一份内存副本, 读请求前重新拉取才能看到其他实例写入的改动。

        * 这里刻意**不回写**本地改动: 读请求若把本实例的旧状态写回, 会覆盖掉
          其他实例刚写入的新状态 (last-write-wins), 也会白白消耗 KV 命令额度。
        '''
        if not self.storage.remote:
            return
        try:
            self.load()
        except Exception as e:
            u.warning(f'[refresh] reload failed, keep in-memory data: {e}')

    def dset(self, name, value):
        '''
        设置一个值
        '''
        self.data[name] = value
        self.dirty = True

    def dget(self, name, default=None):
        '''
        读取一个值
        '''
        try:
            gotdata = self.data[name]
        except KeyError:
            gotdata = default
        return gotdata

    # --- Metrics

    def _ensure_metrics(self) -> bool:
        '''
        确保 `self.data` 中存在 metrics 结构

        远端存储读回的数据可能没有 metrics 字段 (例如首次写入时 metrics 尚未初始化),
        缺字段会让 check_metrics_time / record_metrics 抛 KeyError, 每个请求都 500。

        :return: 是否为本次新建
        '''
        if 'metrics' in self.data:
            return False
        u.debug('[metrics] Metrics data init')
        self.data['metrics'] = {
            'today_is': '',
            'month_is': '',
            'year_is': '',
            'today': {},
            'month': {},
            'year': {},
            'total': {}
        }
        self.dirty = True
        return True

    def metrics_init(self):
        if self._ensure_metrics():
            self.record_metrics()

    def get_metrics_resp(self, json_only: bool = False):
        now = datetime.now(pytz.timezone(env.main.timezone))
        '''
        if json_only:
            # 仅用于调试
            return {
                'time': f'{now}',
                'timezone': env.main.timezone,
                'today_is': self.data['metrics']['today_is'],
                'month_is': self.data['metrics']['month_is'],
                'year_is': self.data['metrics']['year_is'],
                'today': self.data['metrics']['today'],
                'month': self.data['metrics']['month'],
                'year': self.data['metrics']['year'],
                'total': self.data['metrics']['total']
            }
        else:
        '''
        return u.format_dict({
            'time': f'{now}',
            'timezone': env.main.timezone,
            'today_is': self.data['metrics']['today_is'],
            'month_is': self.data['metrics']['month_is'],
            'year_is': self.data['metrics']['year_is'],
            'today': self.data['metrics']['today'],
            'month': self.data['metrics']['month'],
            'year': self.data['metrics']['year'],
            'total': self.data['metrics']['total']
        })

    def check_metrics_time(self) -> None:
        '''
        跨 日 / 月 / 年 检测
        '''
        if not env.util.metrics:
            return
        self._ensure_metrics()

        # get time now
        now = datetime.now(pytz.timezone(env.main.timezone))
        year_is = str(now.year)
        month_is = f'{now.year}-{now.month}'
        today_is = f'{now.year}-{now.month}-{now.day}'

        # - check time
        if self.data['metrics']['today_is'] != today_is:
            u.debug(f'[metrics] today_is changed: {self.data["metrics"]["today_is"]} -> {today_is}')
            self.data['metrics']['today_is'] = today_is
            self.data['metrics']['today'] = {}
        # this month
        if self.data['metrics']['month_is'] != month_is:
            u.debug(f'[metrics] month_is changed: {self.data["metrics"]["month_is"]} -> {month_is}')
            self.data['metrics']['month_is'] = month_is
            self.data['metrics']['month'] = {}
        # this year
        if self.data['metrics']['year_is'] != year_is:
            u.debug(f'[metrics] year_is changed: {self.data["metrics"]["year_is"]} -> {year_is}')
            self.data['metrics']['year_is'] = year_is
            self.data['metrics']['year'] = {}

    def record_metrics(self, path: str = None) -> None:
        '''
        记录调用

        :param path: 访问的路径
        '''

        # check metrics list
        if not path in metrics_list:
            return

        self._ensure_metrics()
        self.check_metrics_time()

        # - record num
        today = self.data['metrics'].setdefault('today', {})
        month = self.data['metrics'].setdefault('month', {})
        year = self.data['metrics'].setdefault('year', {})
        total = self.data['metrics'].setdefault('total', {})

        today[path] = today.get(path, 0) + 1
        month[path] = month.get(path, 0) + 1
        year[path] = year.get(path, 0) + 1
        total[path] = total.get(path, 0) + 1
        # 远端存储下 metrics 只在本实例内存中累加, 不做持久化:
        # 读请求若把整份数据写回 KV, 既会覆盖其他实例的新状态, 也会浪费命令额度。
        if not self.storage.remote:
            self.dirty = True

    # --- Timer check - save data

    def start_timer_check(self, data_check_interval: int = 60):
        '''
        使用 threading 启动下面的 `timer_check()`

        :param data_check_interval: 检查间隔 *(秒)*
        '''
        self.data_check_interval = data_check_interval
        self.timer_thread = threading.Thread(target=self.timer_check, daemon=True)
        self.timer_thread.start()

    def check_device_status(self, trigged_by_timer: bool = False):
        '''
        按情况自动切换状态

        :param trigged_by_timer: 是否由计时器触发 (为 True 将不记录日志)
        '''
        device_status: dict = self.data.get('device_status', {})
        current_status: int = self.data.get('status', 0)  # 获取当前 status，默认为 0
        auto_switch_enabled: bool = env.util.auto_switch_status

        # 检查是否启用自动切换功能，并且当前 status 为 0 或 1
        last_status = self.data['status']
        if auto_switch_enabled:
            if current_status in [0, 1]:
                any_using = any(device.get('using', False) for device in device_status.values())
                if any_using:
                    self.data['status'] = 0
                else:
                    self.data['status'] = 1
                if last_status != self.data['status']:
                    self.dirty = True
                    u.debug(f'[check_device_status] 已自动切换状态 ({last_status} -> {self.data["status"]}).')
                elif not trigged_by_timer:
                    u.debug(f'[check_device_status] 当前状态已为 {current_status}, 无需切换.')
            elif not trigged_by_timer:
                u.debug(f'[check_device_status] 当前状态为 {current_status}, 不适用自动切换.')

    def timer_check(self):
        '''
        定时检查更改并自动保存
        * 根据 `data_check_interval` 参数调整 sleep() 的秒数
        * 需要使用 threading 启动新线程运行
        '''
        u.info(f'[timer_check] started, interval: {self.data_check_interval} seconds.')
        while True:
            sleep(self.data_check_interval)
            try:
                self.check_metrics_time()  # 检测是否跨日
                self.check_device_status(trigged_by_timer=True)  # 检测设备状态并更新 status
                if self.storage.remote:
                    # 远端存储: 只写回本地改动, 不做 "谁更新" 的比较 (避免覆盖其他实例的写入)
                    if self.dirty:
                        self.save()
                else:
                    file_data = self.load(ret=True)
                    if file_data != self.data:
                        self.save()
            except Exception as e:
                u.warning(f'[timer_check] Error: {e}, retrying.')

    # --- check device heartbeat
    # TODO
