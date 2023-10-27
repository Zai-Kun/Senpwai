import os
from sys import platform
from time import sleep as timesleep
from typing import Callable, Any, cast, Iterator
import requests
from string import printable, digits, ascii_letters
import re
import subprocess
from threading import Event
from random_user_agent.user_agent import UserAgent
from random_user_agent.params import OperatingSystem, SoftwareName, SoftwareType, HardwareType
from random import choice as randomchoice
from bs4 import BeautifulSoup, Tag
from shared.global_vars_and_funcs import log_exception, delete_file

PARSER = 'html.parser'
IBYTES_TO_MBS_DIVISOR = 1024*1024
QUALITY_REGEX = re.compile(r'\b(\d{3,4})p\b')
QUALITY_REGEX2 = re.compile(r'\b\d+x(\d+)\b')
NETWORK_RETRY_WAIT_TIME = 5
GITHUB_README_URL = "https://github.com/SenZmaKi/Senpwai/blob/master/README.md"
RESOURCE_MOVED_STATUS_CODES = (301, 302, 307, 308)


def get_new_domain_name_from_readme(site_name: str) -> str:
    """
    Say Animepahe or Gogoanime change their domain name, now Senpwai makes an anime search but it gets a none 200 status code, 
    then it'll assume they changed their domain name. It'll try to extract the new domain name from the readme.
    So if the domain name changes be sure to update it in the readme, specifically in the hyperlinks i.e., [Animepahe](https://animepahe.ru)
    and without an ending / i.e., https://animepahe.ru instead of https://animepahe.ru/ Also test if Senpwai is properly extracting it incase you made a mistake.

    :param site_name: Can be either Animepahe or Gogoanime.
    """
    page_content = CLIENT.get(GITHUB_README_URL).content
    soup = BeautifulSoup(page_content, PARSER)
    new_domain_name =  cast(str, cast(Tag, soup.find('a', text=site_name))['href']).replace("\"", "").replace("\\", "")
    return new_domain_name
    


class Client():

    def __init__(self) -> None:
        self.headers = self.setup_request_headers()

    def setup_request_headers(self) -> dict[str, str]:
        if platform == 'win32':
            operating_systems = [OperatingSystem.WINDOWS.value]
        elif platform == 'linux':
            operating_systems = [OperatingSystem.LINUX.value]
        else:
            operating_systems = [OperatingSystem.DARWIN.value]
        software_names = [SoftwareName.CHROME.value, SoftwareName.FIREFOX.value,
                        SoftwareName.EDGE.value, SoftwareName.OPERA.value]
        software_types = [SoftwareType.WEB_BROWSER.value]
        hardware_types = [HardwareType.COMPUTER.value]
        if platform == 'darwin':
            software_types.append(SoftwareName.SAFARI.value)
        user_agent = randomchoice(UserAgent(limit=1000, software_names=software_names,
                                operating_systems=operating_systems, software_types=software_types,
                                hardware_types=hardware_types).get_user_agents())
        headers = {'User-Agent': user_agent['user_agent']}
        return headers
    
    def append_headers(self, to_append: dict) -> dict:
        to_append.update(self.headers)
        return to_append

    def make_request(self, method: str, url: str, headers: dict | None, cookies={}, stream=False, data: dict | bytes | None = None, json: dict | None = None,  allow_redirects=False, timeout: int | None = None) -> requests.Response:
        if not headers:
            headers = self.headers
        if method == 'GET':
            func = lambda: requests.get(url, headers=headers, stream=stream, cookies=cookies, allow_redirects=allow_redirects, timeout=timeout)
        else:
            func = lambda: requests.post(url, headers=headers, cookies=cookies, data=data, json=json, allow_redirects=allow_redirects)
        return cast(requests.Response, self.network_error_retry_wrapper(func))

    def get(self, url: str, stream=False, headers: dict | None = None, timeout: int | None = None, cookies={}) -> requests.Response:
        return self.make_request("GET", url, headers, stream=stream, timeout=timeout, cookies=cookies)
    
    def post(self, url: str, data: dict | bytes | None = None, json: dict | None = None, headers: dict | None = None, cookies={}, allow_redirects=False) -> requests.Response:
        return self.make_request('POST', url, headers, data=data, json=json, cookies=cookies, allow_redirects=allow_redirects)


    def network_error_retry_wrapper(self, callback: Callable[[], Any]) -> Any:
        while True:
            try:
                return callback()
            except requests.exceptions.RequestException as e:
                    log_exception(e)
                    timesleep(1)

CLIENT = Client()

class QualityAndIndices:
    def __init__(self, quality: int, index: int):
        self.quality = quality
        self.index = index


class AnimeMetadata:
    def __init__(self, poster_url: str, summary: str, episode_count: int, status: str, genres: list[str], release_year: int):
        self.poster_url = poster_url
        self.summary = summary
        self.episode_count = episode_count
        self.airing_status = status
        self.genres = genres
        self.release_year = release_year

    def get_poster_bytes(self) -> bytes:
        response = CLIENT.get(self.poster_url)
        return response.content


def match_quality(potential_qualities: list[str], user_quality: str) -> int:
    detected_qualities: list[QualityAndIndices] = []
    user_quality = user_quality.replace('p', '')
    for idx, potential_quality in enumerate(potential_qualities):
        match = QUALITY_REGEX.search(potential_quality)
        if not match:
            match = QUALITY_REGEX2.search(potential_quality)

        if match:
            quality = cast(str, match.group(1))
            if quality == user_quality:
                return idx
            else:
                if quality.isdigit():
                    detected_qualities.append(
                        QualityAndIndices(int(quality), idx))
    int_user_quality = int(user_quality)
    if len(detected_qualities) <= 0:
        if int_user_quality <= 480:
            return 0
        return -1

    detected_qualities.sort(key=lambda x: x.quality)
    closest = detected_qualities[0]
    for quality in detected_qualities:
        if quality.quality > int_user_quality:
            break
        closest = quality
    return closest.index


def sanitise_title(title: str, all=False, exclude='') -> str:
    if all:
        allowed_chars = set(ascii_letters + digits + exclude)
    else:
        allowed_chars = set(printable) - set('\\/:*?"<>|')
        title = title.replace(':', ' -')
    sanitised = ''.join(filter(lambda char: char in allowed_chars, title))

    return sanitised[:255].rstrip()

def dynamic_episodes_predictor_initialiser_pro_turboencapsulator(start_episode: int, end_episode: int, haved_episodes: list[int]) -> list[int]:
    predicted_episodes_to_download: list[int] = []
    for episode in range(start_episode, end_episode+1):
        if episode not in haved_episodes:
            predicted_episodes_to_download.append(episode)
    return predicted_episodes_to_download


def ffmpeg_is_installed() -> bool:
    try:
        if platform == "win32":
            subprocess.run("ffmpeg")
        else:
            subprocess.run("ffmpeg")
        return True
    except FileNotFoundError:
        return False


class PausableAndCancellableFunction:
    def __init__(self) -> None:
        self.resume = Event()
        self.resume.set()
        self.cancelled = False

    def pause_or_resume(self):
        if self.resume.is_set():
            return self.resume.clear()
        self.resume.set()

    def cancel(self):
        if self.resume.is_set():
            self.cancelled = True

class Download(PausableAndCancellableFunction):
    def __init__(self, link_or_segment_urls: str | list[str], episode_title: str, download_folder_path: str, progress_update_callback: Callable = lambda x: None, file_extension='.mp4', is_hls_download=False, cookies = requests.sessions.RequestsCookieJar()) -> None:
        super().__init__()
        self.link_or_segment_urls = link_or_segment_urls
        self.episode_title = episode_title
        self.file_extension = file_extension
        self.download_folder_path = download_folder_path
        self.progress_update_callback = progress_update_callback
        self.is_hls_download = is_hls_download
        self.cookies = cookies
        file_title = f'{self.episode_title}{self.file_extension}'
        self.file_path = os.path.join(self.download_folder_path, file_title)
        ext = ".ts" if is_hls_download else file_extension
        temporary_file_title = f'{self.episode_title} [Downloading]{ext}'
        self.temporary_file_path = os.path.join(
            self.download_folder_path, temporary_file_title)
        if os.path.isfile(self.temporary_file_path):
            delete_file(self.temporary_file_path)

    def cancel(self):
        return super().cancel()

    def start_download(self):
        download_complete = False
        while not download_complete and not self.cancelled:
            if self.is_hls_download:
                download_complete = self.hls_download()
            else:
                download_complete = self.normal_download()
        if self.cancelled:
            delete_file(self.temporary_file_path)
            return
        delete_file(self.file_path)
        if self.is_hls_download:
            subprocess.run(['ffmpeg', '-i', self.temporary_file_path, '-c', 'copy', self.file_path])
            return delete_file(self.temporary_file_path)
        try:
            return os.rename(self.temporary_file_path, self.file_path)
        except PermissionError: # Maybe they started watching the episode on VLC before it finished downloading now VLC has a handle to the file hence PermissionDenied
            pass

    def hls_download(self) -> bool:
        with open(self.temporary_file_path, "wb") as f:
            for seg in self.link_or_segment_urls:
                response = CLIENT.get(seg)
                self.resume.wait()
                if self.cancelled:
                    return False
                f.write(response.content)
                self.progress_update_callback(1)
            return True

    def normal_download(self) -> bool:
        self.link_or_segment_urls = cast(str, self.link_or_segment_urls)
        response = CLIENT.get(self.link_or_segment_urls, stream=True, timeout=30, cookies=self.cookies)

        def response_ranged(start_byte): 
            self.link_or_segment_urls = cast(str, self.link_or_segment_urls)
            return CLIENT.get(self.link_or_segment_urls, stream=True, headers=CLIENT.append_headers({'Range': f'bytes={start_byte}-'}), timeout=30, cookies=self.cookies)

        total = int(response.headers.get('Content-Length', 0))

        def download(start_byte: int = 0) -> bool:
            mode = 'wb' if start_byte == 0 else 'ab'
            with open(self.temporary_file_path, mode) as file:
                iter_content = cast(Iterator[bytes], response.iter_content(chunk_size=IBYTES_TO_MBS_DIVISOR) if start_byte == 0 else CLIENT.network_error_retry_wrapper(
                    lambda: response_ranged(start_byte).iter_content(chunk_size=IBYTES_TO_MBS_DIVISOR)))
                while True:
                    try:
                        get_data = lambda: next(iter_content)
                        data = cast(bytes, CLIENT.network_error_retry_wrapper(get_data))
                        self.resume.wait()
                        if self.cancelled:
                            return False
                        size = file.write(data)
                        self.progress_update_callback(size)
                    except StopIteration:
                        break

            file_size = os.path.getsize(self.temporary_file_path)
            return True if file_size >= total else download(file_size)
        return download()


if __name__ == "__main__":
    pass
