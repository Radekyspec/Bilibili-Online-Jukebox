from multiprocessing import Process, freeze_support
from asyncio import sleep as async_sleep, gather, wait_for, get_event_loop, run_coroutine_threadsafe, TimeoutError
from aiohttp import ClientSession, request as async_request
from aiofiles import open as async_open
from aioconsole import ainput, aprint
from json import loads
from os import makedirs, remove, execlp, kill
from os.path import realpath, dirname, abspath, join, exists
from zlib import decompress
from queue import Queue, Empty, PriorityQueue
from playsound import playsound
from sys import executable
from time import strftime, localtime, sleep, time_ns
from getpass import getpass
from logging import getLogger, StreamHandler, FileHandler, Formatter, DEBUG, INFO, WARN, WARNING, ERROR, CRITICAL
from psutil import Process as PauseProcess
from random import randint, shuffle
from aiowebsocket.converses import AioWebSocket
from pydub import AudioSegment
from typing import Optional
from configparser import ConfigParser, DEFAULTSECT
from signal import SIGKILL

__version__ = "0.4.12.2"
EXEC_PATH = realpath(dirname(abspath(executable)))
EXEC = join(EXEC_PATH, executable)
PID = Queue()


class BiliDM:
    def __init__(self, live_room_id):
        self.room_id = str(live_room_id)
        self.admin_uid = ["178856569", "108465779"]
        self.wss_url = "wss://broadcastlv.chat.bilibili.com/sub"
        self.fail_time = 0
        self.fail = False
        self.is_pause = False
        self.logger = SongLogger(logger_name="danmaku").get_logger()
        self.song = SearchSongs()
        self.album = Album()
        self.wait_queue: Queue = Queue()
        self.album_queue: Queue = Queue()
        self.playing: Queue = Queue()
        self.pro_queue: Queue = Queue()

    async def startup(self):
        await SongLogin().auto()
        data_raw = "000000{headerLen}0010000100000007000000017b22726f6f6d6964223a{room_id}7d"
        data_raw = data_raw.format(headerLen=hex(27 + len(self.room_id))[2:],
                                   room_id="".join(map(lambda x: hex(ord(x))[2:], list(self.room_id))))
        you_know = [
            "歌曲下载默认超时是30秒! 再也不用担心下载不下来啦! ",
            "弹幕发送 \"点歌(空格)歌名(空格)曲作者\" 就可以开启点歌之旅啦! 曲作者参数是可以不加的哟! ",
            "弹幕发送 \"暂停\" 可以暂停当前歌曲的播放哦! ",
            "弹幕发送 \"播放\" 可以取消暂停当前的歌曲哦! ",
            "弹幕发送 \"切歌\" 可以立即跳过当前歌曲哦! ",
            "主播本人在弹幕发送 \"歌单\" 可以直接播放登录的网易云账号内收藏的歌单哦! ",
            "主播本人在弹幕发送 \"清空歌单\" 可以快捷退出歌单播放模式哦! ",
            "主播或直播间房管在弹幕发送 \"取消点歌\" 可以直接移除点歌列表内所有的歌曲哦! ",
            "弹幕发送 \"撤回点歌\" 可以取消最近一次的点歌哦! 再也不用担心点错歌了! ",
            "点歌姬是付费软件哦! 只需要给作者转账150啥币就可以永久使用了! ",
            "因为作者直播间无人问津, 许多bug尚未得到修复! 若在使用中发现bug请多多汇报哦! ",
            "点歌姬最初是为某位用户专门设计的哦! 你会不会是那个幸运儿呢! ",
            "\"点歌\" 和 \"撤回点歌\" 指令没有用户权限限制哦! ",
            "只有直播间房管或者主播本人才能使用 \"切歌\", \"暂停\" 和 \"播放\" 指令哦! ",
            "只有主播本人才能使用 \"歌单\" 和 \"清空歌单\" 指令哦! ",
            "看不习惯点歌姬的黑框框? 点歌姬GUI版本锐意制作中! ",
            "下一个版本更新是在什么时候? 希望不是明天 (",
            "歌单播放需要在这个窗口进行操作哒! 不要把我丢在一边! 喂! ",
            "点歌指令现在支持使用歌曲id进行点歌啦! 直接把歌曲名称替换成歌曲id就可以了唷! ",
        ]
        async with AioWebSocket(self.wss_url) as aws:
            converse = aws.manipulator
            await converse.send(bytes.fromhex(data_raw))
            try:
                await wait_for(self.acquire_host_uid(), timeout=30)
            except TimeoutError:
                pass
            self.logger.info("[{room_id}] 弹幕服务器已连接. ".format(room_id=self.room_id))
            self.logger.info(f"[{room_id}] 你知道吗: {you_know[randint(0, len(you_know) - 1)]}")
            if " " in EXEC_PATH:
                self.logger.warning(f"[{self.room_id}] 检测到当前运行目录存在空格, 可能导致点歌功能异常, 请切换运行目录后重启本程序.")
            try:
                await wait_for(self.version_checker(), timeout=15)
            except TimeoutError:
                self.logger.error(f"[{self.room_id}] 检查更新超时.")
            tasks = [self.heart_beat(converse), self.receive_dm(converse), self.song_trigger()]
            await gather(*tasks)
        return

    async def version_checker(self):
        self.logger.info(f"[{self.room_id}] 正在检查更新...")
        url = "https://api.github.com/repos/Radekyspec/Bilibili-Online-Jukebox/releases/latest"
        async with async_request("GET", url) as resp:
            resp = await resp.text()
            resp = loads(resp)
        if resp:
            ver = resp["tag_name"]
            if __version__ != ver:
                link = "https://github.com/Radekyspec/Bilibili-Online-Jukebox/releases/"
                self.logger.info(f"[{self.room_id}] 当前有更新的点歌姬可供下载, 请前往 {link} 下载")
                self.logger.info(f"[{self.room_id}] 当前版本: {__version__}, 最新版本: {ver}")
            else:
                self.logger.info(f"[{self.room_id}] 检查更新完成. 当前已运行最新版本.")

    async def heart_beat(self, websockets):
        hb = "00000010001000010000000200000001"
        while not self.fail:
            await async_sleep(20)
            await websockets.send(bytes.fromhex(hb))
            self.fail_time += 1
            self.logger.debug("[{room_id}][HEARTBEAT] Send HeartBeat.".format(room_id=self.room_id))
            if self.fail_time > 5 and not self.fail:
                self.logger.error("[{room_id}] Too many attempts. Danmaku server is no longer available.".format(
                    room_id=self.room_id))
                self.fail = True

    async def acquire_host_uid(self):
        url = "http://api.live.bilibili.com/room/v1/Room/room_init"
        payload = {
            "id": self.room_id,
        }
        # async with ClientSession() as session:
        async with async_request("GET", url, params=payload) as resp:
            resp = await resp.text()
            resp = loads(resp)
        if str(resp["code"]) == "0":
            self.admin_uid.append(str(resp["data"]["uid"]))
            self.admin_uid = list(set(self.admin_uid))
        return

    async def song_trigger(self):
        await async_sleep(0.1)
        try:
            run_coroutine_threadsafe(self.play_song(), get_event_loop())
        except Exception as se:
            self.logger.exception(se)
            self.playing.queue.clear()

    async def receive_dm(self, websockets):
        while not self.fail:
            receive_text = await websockets.receive()
            if receive_text:
                try:
                    run_coroutine_threadsafe(self.process_dm(receive_text), get_event_loop())
                except Exception as se:
                    self.logger.exception(se)
                    self.playing.queue.clear()

    async def process_dm(self, data, is_decompressed=False):
        # 获取数据包的长度，版本和操作类型
        packet_len = int(data[:4].hex(), 16)
        ver = int(data[6:8].hex(), 16)
        op = int(data[8:12].hex(), 16)

        # 有的时候可能会两个数据包连在一起发过来，所以利用前面的数据包长度判断，
        if len(data) > packet_len:
            await self.process_dm(data[packet_len:])
            data = data[:packet_len]

        # 有时会发送过来 zlib 压缩的数据包，这个时候要去解压。
        if ver == 2 and not is_decompressed:
            data = decompress(data[16:])
            await self.process_dm(data, is_decompressed=True)
            return

        # ver 为1的时候为进入房间后或心跳包服务器的回应。op 为3的时候为房间的人气值。
        if ver == 1 and op == 3:
            self.logger.debug("[{room_id}][ATTENTION] {attention}".format(room_id=self.room_id, attention=int(
                data[16:].hex(), 16)))
            self.fail_time = 0
            return

        # ver 不为2也不为1目前就只能是0了，也就是普通的 json 数据。
        # op 为5意味着这是通知消息，cmd 基本就那几个了。
        if op == 5:
            try:
                jd = loads(data[16:].decode("utf-8", errors="ignore"))
                if jd["cmd"] == "DANMU_MSG":
                    user_uid = str(jd["info"][2][0])
                    admin_status = str(jd["info"][2][2])
                    danmaku = str(jd["info"][1]).strip().split()
                    user = str(jd["info"][2][1])
                    if danmaku[0] == "点歌" and danmaku[1:]:
                        song_name = ""
                        for d in danmaku[1:]:
                            song_name += " " + d
                        song_name = song_name.strip()
                        if self.playing.empty() and (
                                self.wait_queue.empty() and self.pro_queue.empty() and self.album_queue.empty()) and (
                                not self.song.song_process.is_alive()):
                            if user_uid in self.admin_uid or (admin_status == "1" and randint(1, randint(1, 100)) == 2):
                                self.pro_queue.put((song_name, True, user))
                                self.song.init(priority=0, keyword=song_name, pro=True)
                            else:
                                self.wait_queue.put((song_name, True, user))
                                self.song.init(priority=0, keyword=song_name)
                            self.logger.info(f"[{self.room_id}] 观众「{user}」点歌成功:「{song_name}」")
                        else:
                            origin_id = self.song.song_id
                            new_id = await self.song.acquire_song_id(song_name)
                            if origin_id is None or new_id is None:
                                pass
                            elif origin_id == new_id:
                                self.logger.error(
                                    f"[{self.room_id}] 观众「{user}」重复点歌! 歌曲「{song_name}」已经位于列表中! ")
                            else:
                                if user_uid in self.admin_uid or (
                                        admin_status == "1" and randint(1, randint(1, 100)) == 2):
                                    self.pro_queue.put((song_name, False, user))
                                    # self.song.init(priority=self.pro_queue.qsize(), keyword=song_name, pro=True)
                                    self.logger.info(f"[{self.room_id}] 观众「{user}」点歌「{song_name}」已加入优先队列.")
                                else:
                                    self.wait_queue.put((song_name, False, user))
                                    # self.song.init(priority=self.wait_queue.qsize() + self.pro_queue.qsize(),
                                    #                keyword=song_name)
                                    self.logger.info(f"[{self.room_id}] 观众「{user}」点歌「{song_name}」已加入队列.")
                    elif danmaku[0] == "切歌" and self.song.song_process.is_alive() and (
                            admin_status == "1" or user_uid in self.admin_uid):
                        self.song.stop_play()
                        self.logger.info(f"[{self.room_id}] 管理「{user}」切歌成功. ")
                    elif danmaku[
                        0] == "暂停" and self.song.song_process.is_alive() and (
                            self.song.song_pid) and not self.is_pause and (
                            admin_status == "1" or user_uid in self.admin_uid):
                        self.logger.info(f"[{self.room_id}] 管理「{user}」暂停了当前播放的歌曲. ")
                        self.is_pause = True
                        p = PauseProcess(self.song.song_pid)
                        p.suspend()
                    elif danmaku[
                        0] == "播放" and self.song.song_process.is_alive() and self.song.song_pid and self.is_pause and (
                            admin_status == "1" or user_uid in self.admin_uid):
                        self.logger.info(f"[{self.room_id}] 管理「{user}」恢复了当前歌曲的播放. ")
                        self.is_pause = False
                        p = PauseProcess(self.song.song_pid)
                        p.resume()
                    elif danmaku[0] == "撤回点歌" and (not self.pro_queue.empty() or not self.wait_queue.empty()):
                        self.logger.info(f"[{self.room_id}] 正在查找「{user}」的点歌记录...")
                        if user_uid in self.admin_uid:
                            search_queue = self.pro_queue
                        else:
                            search_queue = self.wait_queue
                        size = search_queue.qsize()
                        song_list = []
                        while not search_queue.empty():
                            try:
                                song_list.append(search_queue.get(block=False))
                            except Empty:
                                break
                        song_list.reverse()
                        index = 0
                        for details in song_list:
                            if user in details:
                                break
                            else:
                                index += 1
                        if index < size:
                            removed = song_list[index]
                            song_list.remove(removed)
                            song_list.reverse()
                            if user_uid in self.admin_uid:
                                self.pro_queue.queue.clear()
                                for song in song_list:
                                    self.pro_queue.put(song)
                            else:
                                self.wait_queue.queue.clear()
                                for song in song_list:
                                    self.wait_queue.put(song)
                            self.logger.info(f"[{self.room_id}] 成功取消「{user}」最近一次的点歌: 「{removed[0]}」.")
                        else:
                            self.logger.error(f"[{self.room_id}] 未查找到「{user}」的点歌记录.")
                    elif danmaku[0] == "歌单" and user_uid in self.admin_uid:
                        self.logger.info(f"[{self.room_id}] 正在获取登录用户收藏的歌单...")
                        album_dict = await self.album.run()
                        if album_dict:
                            self.logger.info(f"[{self.room_id}] 获取到当前用户歌单列表如下: ")
                            for index in range(album_dict["total"]):
                                albums = f"[{self.room_id}] " + str(index) + ": " + album_dict["data"][index]["name"]
                                await aprint(albums)
                            album_index = await ainput(
                                f"[{self.room_id}] 请输入想要播放的歌单的序号 (如第一个歌单就输入0) (默认为第一个歌单 - 喜欢的音乐) (使用默认歌单请直接按回车): ")
                            if not album_index:
                                album_index = 0
                            try:
                                album_index = int(album_index)
                            except ValueError:
                                self.logger.error(f"[{self.room_id}] 歌单序号只能为数字! ")
                            album_list = await self.album.acquire_album_list(album_index)
                            for song_id in album_list:
                                self.album_queue.put(song_id)
                            # noinspection PyTypeChecker
                            self.logger.info(
                                f"[{self.room_id}] 已将歌单「{album_dict['data'][album_index]['name']}」内共「{len(album_list)}」首歌曲添加至播放列表.")
                    elif danmaku[0] == "清空歌单" and user_uid in self.admin_uid and not self.album_queue.empty():
                        if self.song.song_process.is_alive():
                            self.song.stop_play()
                        self.album_queue.queue.clear()
                        self.logger.info(f"[{self.room_id}] 管理「{user}」清空了歌单播放列表.")
                    elif danmaku[0] == "取消点歌" and (admin_status == "1" or user_uid in self.admin_uid) and (
                            not self.pro_queue.empty() or not self.wait_queue.empty()):
                        if self.song.song_process.is_alive():
                            self.song.stop_play()
                        if not self.pro_queue.empty():
                            self.pro_queue.queue.clear()
                        if not self.wait_queue.empty():
                            self.wait_queue.queue.clear()
                        self.logger.info(f"[{self.room_id}] 管理「{user}」清空了点歌播放列表.")
                    elif danmaku[0] == "重启" and user_uid in self.admin_uid:
                        if self.song.song_process.is_alive():
                            self.song.stop_play()
                        execlp(EXEC, EXEC)
            except Exception as de:
                self.logger.exception(de)

    async def play_song(self):
        while True:
            await async_sleep(1)
            if self.playing.empty() and (
                    not self.wait_queue.empty() or not self.pro_queue.empty() or not self.album_queue.empty()) and (
                    not self.song.song_process.is_alive()):
                album = False
                try:
                    if not self.pro_queue.empty():
                        raw = self.pro_queue.get(block=False)
                        current_song = raw[0]
                        is_first = raw[1]
                        user = raw[2]
                        if not is_first:
                            self.song.init(priority=self.pro_queue.qsize() + 1, keyword=current_song, pro=True)
                    else:
                        if not self.album_queue.empty():
                            current_song = self.album_queue.get(block=False)
                            user = "歌单播放系统"
                            album = True
                        else:
                            raw = self.wait_queue.get(block=False)
                            current_song = raw[0]
                            is_first = raw[1]
                            user = raw[2]
                            if not is_first:
                                self.song.init(priority=self.wait_queue.qsize() + self.pro_queue.qsize() + 1,
                                               keyword=current_song)
                    self.playing.put(current_song)
                except Empty:
                    return
                if self.playing.empty():
                    return
                try:
                    current_song = int(current_song)
                except ValueError:
                    # 输入歌曲名点歌
                    self.logger.info(f"[{self.room_id}] 正在下载:「{current_song}」, 点歌用户:「{user}」...")
                    await self.song.run()
                    self.playing.queue.clear()
                else:
                    # 通过歌曲id点歌
                    if album:
                        # 调用歌单播放系统
                        self.song.song_id = current_song
                        try:
                            await wait_for(fut=self.song.acquire_song_name(), timeout=30)
                        except TimeoutError:
                            self.logger.error(f"[{self.room_id}] 获取歌曲名超时! 正在切换至下一曲...")
                        else:
                            self.logger.info(f"[{self.room_id}] 正在下载:「{self.song.song_name}」, 点歌用户:「{user}」...")
                            await self.song.run_album(song_id=current_song)
                        finally:
                            self.playing.queue.clear()
                    else:
                        # 调用歌曲id点歌
                        self.logger.info(f"[{self.room_id}] 正在下载:「{current_song}」, 点歌用户:「{user}」...")
                        await self.song.run_by_id()
                        self.playing.queue.clear()

    @classmethod
    async def start(cls, room_list: Optional[list] = None):
        if room_list is None:
            room_list = ["22593055"]
        tasks = [BiliDM(startup_room_id).startup() for startup_room_id in room_list]
        await gather(*tasks)


class SearchSongs:
    def __init__(self):
        self.logger = SongLogger(logger_name="search").get_logger()
        self.song_name = None
        self.keyword: PriorityQueue = PriorityQueue()
        self.pro_keyword: PriorityQueue = PriorityQueue()
        self.raw_keyword: PriorityQueue = PriorityQueue()
        self.song_id = None
        self.song_url = None
        self.index = 0
        self.cookies = None
        self.song_pid = None
        self.song_extend = None
        self.song_process = Process()
        PID.queue.clear()

    def reset(self):
        self.song_name = None
        self.song_id = None
        self.song_url = None
        self.index = 0
        self.cookies = None
        self.song_pid = None
        self.song_extend = None
        self.song_process = Process()
        PID.queue.clear()

    def init(self, priority: int, keyword: str, pro: bool = False):
        self.raw_keyword.put((priority, keyword, pro))
        self.pro_upgrade()

    def pro_upgrade(self):
        for i in range(self.raw_keyword.qsize()):
            raw_song = self.raw_keyword.get(block=False)
            priority = raw_song[0]
            keyword = raw_song[1]
            pro = raw_song[2]
            if pro:
                self.pro_keyword.put((priority, keyword))
            else:
                self.keyword.put((priority, keyword))
        self.raw_keyword.queue.clear()

    async def run(self):
        self.reset()
        login = SongLogin()
        login.load_cookies()
        self.cookies = login.cookies
        if not self.pro_keyword.empty():
            raw_keyword = self.pro_keyword.get(block=False)
            pro = True
        else:
            raw_keyword = self.keyword.get(block=False)
            pro = False
        priority = raw_keyword[0]
        keyword = raw_keyword[1]
        if pro:
            self.pro_keyword.put((priority, keyword))
        else:
            self.keyword.put((priority, keyword))
        self.logger.debug("Acquiring song id...")
        try:
            self.song_id = await wait_for(self.acquire_song_id(keyword), timeout=30)
        except TimeoutError:
            self.logger.error(f"下载「{keyword}」超时! 正在切换至下一曲...")
            if pro:
                self.pro_keyword.get()
            else:
                self.keyword.get()
            return
        if self.song_id is not None:
            try:
                self.logger.debug("Acquiring song name...")
                await wait_for(fut=self.acquire_song_name(), timeout=30)
            except TimeoutError:
                self.logger.error(f"下载「{keyword}」超时! 正在切换至下一曲...")
                if pro:
                    self.pro_keyword.get()
                else:
                    self.keyword.get()
                return
            try:
                self.logger.debug("Acquiring download url...")
                await wait_for(fut=self.acquire_song_url(), timeout=30)
            except TimeoutError:
                self.logger.error(f"下载「{keyword}」超时! 正在切换至下一曲...")
                if pro:
                    self.pro_keyword.get()
                else:
                    self.keyword.get()
                return
            if self.song_name and self.song_url:
                self.acquire_format()
                self.logger.debug("Start downloading...")
                try:
                    await wait_for(fut=self.download_song(), timeout=30)
                except TimeoutError:
                    self.logger.error(f"下载「{self.song_name}」超时! 正在切换至下一曲...")
                    if pro:
                        self.pro_keyword.get()
                    else:
                        self.keyword.get()
                    return
                else:
                    self.play_sync_func()
                    if pro:
                        self.pro_keyword.get()
                    else:
                        self.keyword.get()
                    self.logger.info(f"正在播放:「{self.song_name}」...")
                    self.song_process.start()
                    self.song_pid = self.song_process.pid
                    PID.put(self.song_process.pid)

    async def run_by_id(self):
        self.reset()
        login = SongLogin()
        login.load_cookies()
        self.cookies = login.cookies
        if not self.pro_keyword.empty():
            raw_keyword = self.pro_keyword.get(block=False)
            pro = True
        else:
            raw_keyword = self.keyword.get(block=False)
            pro = False
        priority = raw_keyword[0]
        keyword = raw_keyword[1]
        if pro:
            self.pro_keyword.put((priority, keyword))
        else:
            self.keyword.put((priority, keyword))
        """
        try:
            self.logger.debug("Acquiring song id...")
            self.song_id = await wait_for(self.acquire_song_id(keyword), timeout=30)
        except TimeoutError:
            self.logger.error(f"下载「{keyword}」超时! 正在切换至下一曲...")
            if pro:
                self.pro_keyword.get()
            else:
                self.keyword.get()
        """
        self.song_id = keyword
        if self.song_id is not None:
            try:
                self.logger.debug("Acquiring song name...")
                await wait_for(fut=self.acquire_song_name(), timeout=30)
            except TimeoutError:
                self.logger.error(f"下载「{keyword}」超时! 正在切换至下一曲...")
                if pro:
                    self.pro_keyword.get()
                else:
                    self.keyword.get()
                return
            try:
                self.logger.debug("Acquiring download url...")
                await wait_for(fut=self.acquire_song_url(), timeout=30)
            except TimeoutError:
                self.logger.error(f"下载「{keyword}」超时! 正在切换至下一曲...")
                if pro:
                    self.pro_keyword.get()
                else:
                    self.keyword.get()
                return
            if self.song_name and self.song_url:
                self.acquire_format()
                self.logger.debug("Start downloading...")
                try:
                    await wait_for(fut=self.download_song(), timeout=30)
                except TimeoutError:
                    self.logger.error(f"下载「{self.song_name}」超时! 正在切换至下一曲...")
                    if pro:
                        self.pro_keyword.get()
                    else:
                        self.keyword.get()
                    return
                else:
                    self.play_sync_func()
                    if pro:
                        self.pro_keyword.get()
                    else:
                        self.keyword.get()
                    self.logger.info(f"正在播放:「{self.song_name}」...")
                    self.song_process.start()
                    self.song_pid = self.song_process.pid
                    PID.put(self.song_process.pid)

    async def run_album(self, song_id):
        self.reset()
        login = SongLogin()
        login.load_cookies()
        self.cookies = login.cookies
        self.logger.debug("Acquiring song id...")
        try:
            self.song_id = await wait_for(self.acquire_song_id(song_id), timeout=30)
        except TimeoutError:
            self.logger.error(f"下载「{song_id}」超时! 正在切换至下一曲...")
        if self.song_id is not None:
            try:
                self.logger.debug("Acquiring song name...")
                await wait_for(fut=self.acquire_song_name(), timeout=30)
            except TimeoutError:
                self.logger.error(f"下载「{self.song_id}」超时! 正在切换至下一曲...")
                return
            try:
                self.logger.debug("Acquiring download url...")
                await wait_for(fut=self.acquire_song_url(), timeout=30)
            except TimeoutError:
                self.logger.error(f"下载「{self.song_id}」超时! 正在切换至下一曲...")
                return
            if self.song_name and self.song_url:
                self.acquire_format()
                self.logger.debug("Start downloading...")
                try:
                    await wait_for(fut=self.download_song(), timeout=30)
                except TimeoutError:
                    self.logger.error(f"下载「{self.song_name}」超时! 正在切换至下一曲...")
                    return
                else:
                    self.play_sync_func()
                    self.logger.info(f"正在播放:「{self.song_name}」...")
                    self.song_process.start()
                    self.song_pid = self.song_process.pid
                    PID.put(self.song_process.pid)

    async def acquire_song_id(self, keyword):
        url = "https://netease.a-soul.cloud/cloudsearch"
        payload = {
            "keywords": keyword,
            "cookie": self.cookies,
            "realIP": "114.114.114.114",
        } if self.cookies is not None else {
            "keywords": keyword,
            "realIP": "114.114.114.114",
        }
        async with async_request("GET", url, params=payload) as resp:
            resp = await resp.text()
            resp = loads(resp)
        try:
            song_id = resp["result"]["songs"][0]["id"]
        except KeyError:
            self.logger.error("歌曲「{song_name}」不存在! 指定作曲家试试? ".format(song_name=keyword))
            return
        return song_id

    async def acquire_song_name(self):
        url = "https://netease.a-soul.cloud/song/detail"
        payload = {
            "ids": self.song_id,
            "cookie": self.cookies,
            "realIP": "114.114.114.114",
        } if self.cookies is not None else {
            "ids": self.song_id,
            "realIP": "114.114.114.114",
        }
        async with async_request("GET", url, params=payload) as resp:
            resp = await resp.text()
            resp = loads(resp)
        try:
            self.song_name = resp["songs"][0]["name"]
        except KeyError:
            self.logger.error("歌曲「{song_name}」不存在! 指定作曲家试试? ".format(song_name=self.song_id))
        return

    async def acquire_song_url(self):
        url = "https://netease.a-soul.cloud/song/url"
        payload = {
            "id": self.song_id,
            "cookie": self.cookies,
            "realIP": "114.114.114.114",
        } if self.cookies is not None else {
            "id": self.song_id,
            "realIP": "114.114.114.114",
        }
        async with async_request("GET", url, params=payload) as resp:
            resp = await resp.text()
            resp = loads(resp)
        try:
            self.song_url = resp["data"][0]["url"]
        except KeyError:
            pass
        if not self.song_url:
            self.index += 1
            await self.run()
            return
        return

    def acquire_format(self):
        if self.song_url:
            self.song_extend = str(self.song_url.split(".")[-1])

    def format_converter(self):
        if self.song_extend != "mp3":
            self.logger.debug("Need .mp3, having .{format} instead. Trying to convert...".format(
                format=self.song_extend))
            AudioSegment.from_file(join(EXEC_PATH,
                                        "temp.{extend}".format(extend=self.song_extend))).export(
                join(EXEC_PATH,
                     "temp.mp3"), format="mp3")
            self.song_extend = "mp3"
            self.logger.debug("Convert complete! ")

    async def download_song(self):
        if self.song_url:
            async with ClientSession() as session:
                async with session.get(self.song_url) as resp:
                    async with async_open(
                            join(EXEC_PATH,
                                 "temp.{extend}".format(extend=self.song_extend)),
                            "wb") as r:
                        async for chunk in resp.content.iter_chunked(1024):
                            await r.write(chunk)
                        await r.close()
                await session.close()
            return

    def play_sync_func(self):
        self.format_converter()
        self.logger.debug("Ready to play!")
        self.song_process = Process(target=playsound,
                                    args=("file:///{path}".format(
                                        path=join(EXEC_PATH,
                                                  "temp.{extend}".format(extend=self.song_extend))),),
                                    daemon=True)

    def stop_play(self):
        self.song_process.terminate()


class SongLogin:
    def __init__(self):
        self.logger = SongLogger(logger_name="login").get_logger()
        self.phone = None
        self.email = None
        self.password = None
        self.cookies = None
        self.config_parser = BaseConfig()

    def init(self, phone: Optional[str] = None, email: Optional[str] = None, password: Optional[str] = None):
        self.phone = phone
        self.email = email
        self.password = password

    async def phone_login(self):
        url = "https://netease.a-soul.cloud/login/cellphone"
        payload = {
            "phone": self.phone,
            "password": self.password,
            "realIP": "114.114.114.114",
        }
        async with async_request("GET", url, params=payload) as resp:
            resp = await resp.text()
            resp = loads(resp)
        try:
            self.cookies = resp["cookie"]
        except KeyError:
            self.logger.error(f"[LOGIN] 登录失败! 原因: {resp}")
            return
        else:
            self.logger.info(
                f"[LOGIN] 登录成功. 使用令牌: {self.cookies[:20]}******************************************************.")
            return

    async def email_login(self):
        url = "https://netease.a-soul.cloud/login"
        payload = {
            "email": self.email,
            "password": self.password,
            "realIP": "114.114.114.114",
        }
        async with async_request("GET", url, params=payload) as resp:
            resp = await resp.text()
            resp = loads(resp)
        try:
            self.cookies = resp["cookie"]
        except KeyError:
            self.logger.error(f"[LOGIN] 登录失败! 原因: {resp}")
            return
        else:
            self.logger.info(
                f"[LOGIN] 登录成功. 使用令牌: {self.cookies[:20]}******************************************************.")
            return

    def save_cookies(self):
        if self.cookies:
            self.config_parser.save("Netease", "cookies", self.cookies)
        return

    def load_cookies(self):
        if self.config_parser.has_section("Netease") and self.config_parser.has_option(
                "Netease", "cookies") and self.config_parser.parser["Netease"]["cookies"]:
            self.cookies = self.config_parser.parser["Netease"]["cookies"]
        return

    async def refresh_login(self):
        url = "https://netease.a-soul.cloud/login/refresh/"
        payload = {
            "cookie": self.cookies,
            "realIP": "114.114.114.114",
        } if self.cookies else None
        async with async_request("GET", url, params=payload) as resp:
            resp = await resp.text()
            resp = loads(resp)
        if resp["code"] != 200:
            self.cookies = None
        return

    async def auto(self):
        self.logger.info("正在恢复登录...")
        self.load_cookies()
        await self.refresh_login()
        if not self.cookies:
            self.logger.warning("[LOGIN] 登录令牌无效或为空. ")
            mode = str(await ainput("[LOGIN] 请选择网易云登录模式 (输入1为使用账号密码登录, 输入2为使用邮箱密码登录) (不需要登录请按回车): "))
            if mode and mode == "1":
                self.phone = str(getpass("[LOGIN] 请输入手机号, 输入完毕后回车 (手机号不会显示): "))
                self.password = str(getpass("[LOGIN] 请输入密码, 输入完毕后回车 (密码不会显示): "))
                await self.phone_login()
                self.save_cookies()
            elif mode and mode == "2":
                self.email = str(getpass("[LOGIN] 请输入邮箱, 输入完毕后回车 (邮箱不会显示): "))
                self.password = str(getpass("[LOGIN] 请输入密码, 输入完毕后回车 (密码不会显示): "))
                await self.email_login()
                self.save_cookies()


class Album:
    """
    歌单播放逻辑：
    1. 调用acquire_login_status鉴权
    2. 获取当前登录用户的歌单列表，存储并返回，让用户进行选择
    3. 获取并返回对应歌单内歌曲id列表
    4. （在外部方法）将歌曲加入album_queue并播放
    4.1. album_queue被设计为排在优先队列之后，点歌队列之前，提供切歌和取消播放两个接口
    4.2. 取消播放即代表清空album_queue
    4.3. album_queue为随机播放
    """

    def __init__(self):
        self.uid = None
        self.cookies = None
        self.album_dict = {
            "total": 0,
            "data": [],
        }
        self.logger = SongLogger(logger_name="album").get_logger()

    async def run(self):
        if await self.acquire_login_status():
            await self.acquire_uid()
            await self.acquire_user_playlist()
            return self.album_dict
        return None

    # 一定需要先调用此方法鉴权
    async def acquire_login_status(self):
        login = SongLogin()
        login.load_cookies()
        await login.refresh_login()
        self.cookies = login.cookies
        if not self.cookies:
            self.logger.error("[ALBUM] 使用该功能需要登录, 您还没有登录哦~")
            return None
        return self.cookies

    async def acquire_uid(self):
        url = "https://netease.a-soul.cloud/login/status"
        payload = {
            "cookie": self.cookies,
            "realIP": "114.114.114.114",
        }
        async with async_request("GET", url, params=payload) as resp:
            resp = await resp.text()
            resp = loads(resp)
        self.uid = resp["data"]["account"]["id"]

    async def acquire_user_playlist(self):
        url = "https://netease.a-soul.cloud/user/playlist"
        payload = {
            "uid": self.uid,
            "cookie": self.cookies,
            "limit": "9999",
            "realIP": "114.114.114.114",
        }
        async with async_request("GET", url, params=payload) as resp:
            resp = await resp.text()
            resp = loads(resp)
        # 返回可供选择的歌单列表
        self.album_dict["total"] = len(resp["playlist"])
        for i in range(len(resp["playlist"])):
            detail: dict = {
                "id": resp["playlist"][i]["id"],
                "name": resp["playlist"][i]["name"],
            }
            self.album_dict["data"].append(detail)

    # 单独调用此方法来获取歌单内所有歌曲
    async def acquire_album_list(self, index):
        # noinspection PyTypeChecker
        album_id = self.album_dict["data"][index]["id"]
        url = "https://netease.a-soul.cloud/playlist/track/all"
        payload = {
            "id": album_id,
            "cookie": self.cookies,
            "realIP": "114.114.114.114",
        }
        async with async_request("GET", url, params=payload) as resp:
            resp = await resp.text()
            resp = loads(resp)
        album_id_list = []
        for i in range(len(resp["songs"])):
            album_id_list.append(resp["songs"][i]["id"])
        shuffle(album_id_list)
        return album_id_list


class SongLogger:
    def __init__(self, level: Optional[str] = "INFO", logger_name: Optional[str] = "logger"):
        self.logger = None
        self.level = level
        self.name = logger_name
        self.set_logger()

    def set_logger(self):
        if self.level and self.level == "INFO":
            self.level = INFO
        elif self.level and self.level == "DEBUG":
            self.level = DEBUG
        elif self.level and self.level == "WARNING":
            self.level = WARNING
        elif self.level and self.level == "ERROR":
            self.level = ERROR
        elif self.level and self.level == "WARN":
            self.level = WARN
        elif self.level and self.level == "CRITICAL":
            self.level = CRITICAL

        try:
            makedirs(join(EXEC_PATH, "logs"))
        except (FileExistsError, OSError):
            pass

        self.logger = getLogger(self.name)
        self.logger.setLevel(self.level)
        stream_handler = StreamHandler()
        stream_handler.setLevel(self.level)
        file_handler = FileHandler(
            filename=join(EXEC_PATH, "logs",
                          "{log_time}.log".format(log_time=strftime("%Y-%m-%d", localtime()))),
            mode="a",
            encoding="utf-8",
        )
        file_handler.setLevel(self.level)
        formatter = Formatter(fmt="%(asctime)s - [%(levelname)s] %(message)s")
        stream_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)
        self.logger.handlers.clear()
        self.logger.addHandler(stream_handler)
        self.logger.addHandler(file_handler)
        return

    def get_logger(self):
        return self.logger


class BaseConfig:
    def __init__(self):
        self.parser = ConfigParser()
        try:
            makedirs(join(EXEC_PATH, "config"))
        except FileExistsError:
            pass
        if not exists(join(EXEC_PATH, "config", "config.ini")) or not (self.verify_room_id() or self.verify_cookies()):
            self.init_config()
        self.load_parser()

    def load_parser(self):
        self.parser.clear()
        self.parser.read(join(EXEC_PATH, "config", "config.ini"), encoding="utf-8")
        return self.parser

    def init_config(self):
        self.parser.clear()
        try:
            remove(join(EXEC_PATH, "config", "config.ini"))
        except FileNotFoundError:
            pass
        self.parser.read_dict({
            "Users": {
                "room_id": "",
            },
            "Netease": {
                "cookies": "",
            },
        })
        self.parser.write(open(join(EXEC_PATH, "config", "config.ini"), "w"))
        return

    def verify_room_id(self):
        self.parser.clear()
        self.parser.read(join(EXEC_PATH, "config", "config.ini"), encoding="utf-8")
        results = [
            True if (self.parser.has_section("Users") and self.parser.has_section("Users") != DEFAULTSECT) else False,
            True if (self.parser.has_option(
                "Users", "room_id") and self.parser.has_option("Users", "room_id") != DEFAULTSECT) else False,
        ]
        return all(results)

    def verify_cookies(self):
        self.parser.clear()
        self.parser.read(join(EXEC_PATH, "config", "config.ini"), encoding="utf-8")
        results = [
            True if (self.parser.has_section("Netease") and self.parser.has_section(
                "Netease") != DEFAULTSECT) else False,
            True if (self.parser.has_option(
                "Netease", "cookies") and self.parser.has_option("Netease", "cookies") != DEFAULTSECT) else False,
        ]
        return all(results)

    def has_section(self, section):
        if self.parser.has_section(section):
            return True
        else:
            return False

    def has_option(self, section, option):
        try:
            if self.parser.has_option(section, option):
                return True
            else:
                return False
        except AttributeError:
            return False

    def save(self, section, option, content=""):
        self.parser.clear()
        self.parser.read(join(EXEC_PATH, "config", "config.ini"), encoding="utf-8")
        if not self.parser.has_section(section):
            self.parser[section] = {}
        self.parser[section][option] = content
        self.parser.write(open(join(EXEC_PATH, "config", "config.ini"), "w"))
        return


__name__ = "__main__"
while __name__ == "__main__":
    freeze_support()
    logger = SongLogger(level="INFO", logger_name="errors").get_logger()
    error_stream_handler = StreamHandler()
    error_stream_handler.setLevel(CRITICAL)
    error_file_handler = FileHandler(
        filename=join(EXEC_PATH, "logs", "{log_time}.log".format(log_time=strftime("%Y-%m-%d", localtime()))),
        mode="a",
        encoding="utf-8",
    )
    error_file_handler.setLevel(INFO)
    error_formatter = Formatter(fmt="%(asctime)s - [%(levelname)s] %(message)s")
    error_stream_handler.setFormatter(error_formatter)
    error_file_handler.setFormatter(error_formatter)
    logger.handlers.clear()
    logger.addHandler(error_stream_handler)
    logger.addHandler(error_file_handler)
    room_id = BaseConfig().parser["Users"]["room_id"]
    if not room_id:
        room_id = input(
            "{log_time},{ns} - [INFO][INIT] 请输入直播间号 (纯数字), 输入完毕后回车: ".format(
                log_time=strftime("%Y-%m-%d %H:%M:%S", localtime()), ns=time_ns() % 1000))
    try:
        room_id = int(room_id)
    except ValueError:
        BaseConfig().save("Users", "room_id", "")
        logger.critical("[INIT] 直播间号只能为数字! ")
        sleep(0.1)
        continue
    else:
        BaseConfig().save("Users", "room_id", str(room_id))
        __name__ = "__started__"
        try:
            get_event_loop().run_until_complete(BiliDM.start([room_id]))
        except Exception as e:
            logger.exception(e)
            logger.critical(f"[{room_id}] 程序发生错误, 即将自动重启...")
            logger.critical(f"[{room_id}] 错误已经被记录, 请将logs目录下的日志文件发送给作者.")
            if not PID.empty():
                try:
                    kill(PID.get(block=False), SIGKILL)
                except (Empty, OSError):
                    pass
            execlp(EXEC, EXEC)
