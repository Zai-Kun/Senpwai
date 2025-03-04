from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSystemTrayIcon, QSpacerItem, QLayoutItem
from PyQt6.QtCore import Qt, QThread, QMutex, pyqtSignal, QTimer
from shared.global_vars_and_funcs import settings, KEY_ALLOW_NOTIFICATIONS, KEY_TRACKED_ANIME, KEY_AUTO_DOWNLOAD_SITE, KEY_MAX_SIMULTANEOUS_DOWNLOADS, PAHE, KEY_CHECK_FOR_NEW_EPS_AFTER
from shared.global_vars_and_funcs import set_minimum_size_policy, remove_from_queue_icon_path, move_up_queue_icon_path, move_down_queue_icon_path
from shared.global_vars_and_funcs import PAHE, GOGO, DUB, download_window_bckg_image_path, open_folder, pause_icon_path, resume_icon_path, cancel_icon_path
from shared.app_and_scraper_shared import Download, IBYTES_TO_MBS_DIVISOR, CLIENT, PausableAndCancellableFunction, ffmpeg_is_installed, dynamic_episodes_predictor_initialiser_pro_turboencapsulator, sanitise_title, RESOURCE_MOVED_STATUS_CODES
from windows.main_actual_window import MainWindow, Window
from shared.shared_classes_and_widgets import StyledLabel, StyledButton, ScrollableSection, ProgressBarWithoutButtons, ProgressBarWithButtons, AnimeDetails, FolderButton, OutlinedLabel, IconButton, HorizontalLine, Anime, Icon, ProgressBarWithoutButtons
from typing import Callable, cast, Any
import os
import requests
from scrapers import gogo
from scrapers import pahe
from threading import Event
from gc import collect as gccollect


class CurrentAgainstTotal(StyledLabel):
    def __init__(self, total: int, units: str, font_size=30, parent: QWidget | None = None):
        super().__init__(parent, font_size)
        self.total = total
        self.current = 0
        self.units = units
        # This is to ensure that even when DownloadedEpisodeCount overwrides update_count, the parent's update count still gets called during parent class initialisation
        CurrentAgainstTotal.update_count(self, 0)

    def update_count(self, added: int):
        self.current += added
        self.setText(f"{self.current}/{self.total} {self.units}")
        set_minimum_size_policy(self)
        self.update()


class HlsEstimatedSize(CurrentAgainstTotal):
    def __init__(self, download_window, total_episode_count: int):
        super().__init__(0, "MBs", parent=download_window)
        self.download_window = cast(Download, download_window)
        self.total_episode_count = total_episode_count
        self.current_episode_count = 0
        self.sizes_for_each_eps: list[int] = []

    def update_count(self, added: int):
        if added == 0:
            self.total -= self.current
            self.total_episode_count -= 1
        else:
            self.sizes_for_each_eps.append(added)
        count = len(self.sizes_for_each_eps)
        if count > 0:
            new_current = sum(self.sizes_for_each_eps)
            self.current = new_current
            self.total = round((new_current / count) *
                               self.total_episode_count)
        super().update_count(0)


class DownloadedEpisodeCount(CurrentAgainstTotal):
    def __init__(self, download_window, total_episodes: int, anime_title: str,
                 anime_folder_path: str):
        self.download_window = cast(DownloadWindow, download_window)
        self.download_window = download_window
        self.anime_folder_path = anime_folder_path
        self.anime_title = anime_title
        self.cancelled = False
        super().__init__(total_episodes, "eps", 30, download_window)

    def reinitialise(self, new_total: int, new_anime_title: str, new_anime_folder_path: str):
        self.cancelled = False
        self.current = 0
        self.total = new_total
        self.anime_folder_path = new_anime_folder_path
        self.anime_title = new_anime_title
        super().update_count(0)

    def is_complete(self) -> bool:
        return self.current >= self.total

    def update_count(self, added_episode_count: int):
        super().update_count(added_episode_count)
        complete = self.is_complete()
        if complete and self.total != 0 and cast(bool, settings[KEY_ALLOW_NOTIFICATIONS]):
            self.download_window.main_window.tray_icon.make_notification(
                "Download Complete", self.anime_title, True, lambda: open_folder(self.anime_folder_path))
        if complete or self.cancelled:
            self.start_next_download()

    def start_next_download(self):
        queued_downloads_count = len(
            self.download_window.download_queue.get_queued_downloads())
        if queued_downloads_count > 1:
            self.download_window.start_download()
        gccollect()


class CancelAllButton(StyledButton):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, 25, "white", "red", "#ED2B2A", "#990000")
        self.setText("CANCEL")
        self.cancel_callback: Callable = lambda: None
        self.clicked.connect(self.cancel)
        self.show()

    def cancel(self):
        self.cancel_callback()


class PauseAllButton(StyledButton):
    def __init__(self, download_is_active: Callable, parent: QWidget | None = None):
        super().__init__(parent, 25, "white", "#FFA41B", "#FFA756", "#F86F03")
        self.setText("PAUSE")
        self.pause_callback: Callable = lambda: None
        self.download_is_active = download_is_active
        self.not_paused_style_sheet = self.styleSheet()
        styles_to_overwride = """
                QPushButton {
                background-color: #FFA756;
            }
            QPushButton:hover {
                background-color: #FFA41B;
            }
            QPushButton:pressed {
                background-color: #F86F03;
            }
            """
        self.paused_style_sheet = self.not_paused_style_sheet + styles_to_overwride
        self.setStyleSheet(self.not_paused_style_sheet)
        self.paused = False
        self.clicked.connect(self.pause_or_resume)
        self.show()

    def pause_or_resume(self):
        if self.download_is_active():
            self.paused = not self.paused
            self.pause_callback()
            if self.paused:
                self.setText("RESUME")
                self.setStyleSheet(self.paused_style_sheet)

            elif not self.paused:
                self.setText("PAUSE")
                self.setStyleSheet(self.not_paused_style_sheet)
            self.update()
            set_minimum_size_policy(self)


class QueuedDownload(QWidget):
    def __init__(self, anime_details: AnimeDetails, progress_bar: ProgressBarWithoutButtons, download_queue):
        super().__init__()
        label = StyledLabel(font_size=14)
        self.anime_details = anime_details
        self.progress_bar = progress_bar
        label.setText(anime_details.anime.title)
        set_minimum_size_policy(label)
        download_queue = cast(DownloadQueue, download_queue)
        self.main_layout = QHBoxLayout()
        self.up_button = IconButton(download_queue.up_icon, 1.1, self)
        self.up_button.clicked.connect(
            lambda: download_queue.move_queued_download(self, "up"))
        self.down_button = IconButton(download_queue.down_icon, 1.1, self)
        self.down_button.clicked.connect(
            lambda: download_queue.move_queued_download(self, "down"))
        self.remove_button = IconButton(download_queue.remove_icon,  1.1, self)
        self.remove_button.clicked.connect(
            lambda: download_queue.remove_queued_download(self))
        self.main_layout.addWidget(label)
        self.main_layout.addWidget(self.up_button)
        self.main_layout.addWidget(self.down_button)
        self.main_layout.addWidget(self.remove_button)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.setLayout(self.main_layout)


class DownloadQueue(QWidget):
    def __init__(self, download_window: QWidget):
        super().__init__(download_window)
        label = OutlinedLabel(None, 1, 25)
        label.setStyleSheet("""
            OutlinedLabel {
                color: #4169e1;
                font-size: 25px;
                font-family: "Berlin Sans FB Demi";
                    }
                    """)
        label.setText("Download queue")
        main_layout = QVBoxLayout()
        main_layout.addWidget(label)
        self.queued_downloads_layout = QVBoxLayout()
        self.queued_downloads_scrollable = ScrollableSection(
            self.queued_downloads_layout)
        line = HorizontalLine(parent=self)
        line.setFixedHeight(6)
        main_layout.addWidget(line)
        main_layout.addWidget(self.queued_downloads_scrollable)
        self.setLayout(main_layout)
        self.up_icon = Icon(30, 30, move_up_queue_icon_path)
        self.down_icon = Icon(30, 30, move_down_queue_icon_path)
        self.remove_icon = Icon(30, 30, remove_from_queue_icon_path)

    def remove_buttons_from_queued_download(self, queued_download: QueuedDownload):
        queued_download.main_layout.removeWidget(queued_download.up_button)
        queued_download.main_layout.removeWidget(queued_download.down_button)
        queued_download.main_layout.removeWidget(queued_download.remove_button)
        queued_download.up_button.deleteLater()
        queued_download.down_button.deleteLater()
        queued_download.remove_button.deleteLater()

    def add_queued_download(self, anime_details: AnimeDetails, progress_bar: ProgressBarWithoutButtons):
        self.queued_downloads_layout.addWidget(
            QueuedDownload(anime_details, progress_bar, self), alignment=Qt.AlignmentFlag.AlignTop)

    def move_queued_download(self, to_move: QueuedDownload, up_or_down="up"):
        queued_downloads = self.get_queued_downloads()
        for idx, queued in enumerate(queued_downloads):
            if queued == to_move:
                if up_or_down == "up" and idx-1 > 0:
                    self.queued_downloads_layout.removeWidget(to_move)
                    self.queued_downloads_layout.insertWidget(idx-1, to_move)
                elif up_or_down == "down" and idx+1 < len(queued_downloads):
                    self.queued_downloads_layout.removeWidget(to_move)
                    self.queued_downloads_layout.insertWidget(idx+1, to_move)

    def remove_queued_download(self, queued_download: QueuedDownload):
        for widget in self.get_queued_downloads():
            if widget == queued_download:
                self.queued_downloads_layout.removeWidget(widget)
                widget.deleteLater()

    def get_first_queued_download(self) -> QueuedDownload:
        first_queued_download = cast(
            QueuedDownload, cast(QLayoutItem, self.queued_downloads_layout.itemAt(0)).widget())
        return first_queued_download

    def remove_first_queued_download(self):
        wid = self.get_first_queued_download()
        self.queued_downloads_layout.removeWidget(wid)
        wid.deleteLater()

    def get_queued_downloads(self) -> list[QueuedDownload]:
        count = self.queued_downloads_layout.count()
        return [cast(QueuedDownload, cast(QLayoutItem, self.queued_downloads_layout.itemAt(index)).widget()) for index in range(count)]


class DownloadWindow(Window):
    def __init__(self, main_window: MainWindow):
        super().__init__(main_window, download_window_bckg_image_path)
        self.main_window = main_window
        self.main_layout = QVBoxLayout()
        self.progress_bars_layout = QVBoxLayout()
        progress_bars_scrollable = ScrollableSection(self.progress_bars_layout)
        top_section_widget = QWidget()
        top_section_layout = QVBoxLayout()
        top_section_widget.setLayout(top_section_layout)
        first_row_of_progress_bar_widget = QWidget()
        self.first_row_of_progress_bar_layout = QHBoxLayout()
        first_row_of_progress_bar_widget.setLayout(
            self.first_row_of_progress_bar_layout)
        second_row_of_buttons_widget = QWidget()
        self.second_row_of_buttons_layout = QHBoxLayout()
        second_row_of_buttons_widget.setLayout(
            self.second_row_of_buttons_layout)
        top_section_layout.addWidget(first_row_of_progress_bar_widget)
        top_section_layout.addWidget(second_row_of_buttons_widget)
        self.main_layout.addWidget(top_section_widget)
        self.main_layout.addWidget(progress_bars_scrollable)
        main_widget = ScrollableSection(self.main_layout)
        self.full_layout.addWidget(main_widget)
        self.setLayout(self.full_layout)
        self.first_download_since_app_start = True
        self.current_anime_progress_bar: ProgressBarWithoutButtons
        self.hls_est_size: HlsEstimatedSize | None = None
        self.download_queue: DownloadQueue
        self.pause_button: PauseAllButton
        self.cancel_button: CancelAllButton
        self.folder_button: FolderButton
        self.downloaded_episode_count: DownloadedEpisodeCount
        self.auto_download_timer = QTimer(self)
        self.auto_download_timer.timeout.connect(self.start_auto_download)
        self.setup_auto_download_timer()
        self.auto_download_thread: AutoDownloadThread | None = None

    def setup_auto_download_timer(self):
        self.auto_download_timer.stop()
        self.auto_download_timer.start(
            cast(int, settings[KEY_CHECK_FOR_NEW_EPS_AFTER]) * 1000 * 60 * 60)

    def clean_out_auto_download_thread(self):
        self.auto_download_thread = None

    def start_auto_download(self):
        tracked_anime = cast(list[str], settings[KEY_TRACKED_ANIME])

        # We only spawn a new thread if one wasn't already running to avoid overwriding the reference to the previous one causing it to get garbage collected/destroyed
        # Cause it can cause this error "QThread: Destroyed while thread is still running"
        if tracked_anime != [] and not self.auto_download_thread:
            self.auto_download_thread = AutoDownloadThread(self, tracked_anime,
                                                           self.main_window.tray_icon, self.clean_out_auto_download_thread)
            self.auto_download_thread.start()

    def initiate_download_pipeline(self, anime_details: AnimeDetails):
        if self.first_download_since_app_start:
            self.pause_icon = Icon(30, 30, pause_icon_path)
            self.resume_icon = Icon(30, 30, resume_icon_path)
            self.cancel_icon = Icon(30, 30, cancel_icon_path)
            self.download_queue = DownloadQueue(self)

        if anime_details.sub_or_dub == DUB:
            anime_details.anime.page_link = anime_details.dub_page_link
        if anime_details.site == PAHE:
            return PaheGetTotalPageCountThread(self, anime_details, self.pahe_get_episode_page_links).start()
        self.gogo_get_download_page_links(anime_details)

    def pahe_get_episode_page_links(self, anime_details: AnimeDetails, page_count: int):
        episode_page_progress_bar = ProgressBarWithButtons(
            None, "Getting episode page links", "", page_count, "pgs", 1, self.pause_icon, self.resume_icon, self.cancel_icon, lambda: None, lambda: None)
        self.progress_bars_layout.insertWidget(
            0, episode_page_progress_bar)
        PaheGetEpisodePageLinksThread(self, anime_details, anime_details.predicted_episodes_to_download[0], anime_details.predicted_episodes_to_download[-1],
                                      self.pahe_get_download_page_links, episode_page_progress_bar).start()

    def gogo_get_download_page_links(self, anime_details: AnimeDetails):
        next_func = self.get_hls_links if anime_details.is_hls_download else self.get_direct_download_links
        return GogoGetDownloadPageLinksThread(self, anime_details, next_func).start()

    def pahe_get_download_page_links(self, anime_details: AnimeDetails, episode_page_links: list[str]):
        episode_page_links = [episode_page_links[eps-anime_details.predicted_episodes_to_download[0]]
                              for eps in anime_details.predicted_episodes_to_download]
        download_page_progress_bar = ProgressBarWithButtons(
            self, "Fetching download page links", "", len(episode_page_links), "eps", 1, self.pause_icon, self.resume_icon, self.cancel_icon, lambda: None, lambda: None)
        self.progress_bars_layout.insertWidget(0, download_page_progress_bar)
        PaheGetDownloadPageThread(self, anime_details, episode_page_links,
                                  self.get_direct_download_links, download_page_progress_bar).start()

    def get_hls_links(self, anime_details: AnimeDetails, episode_page_links: list[str]):
        if not ffmpeg_is_installed():
            return self.main_window.create_and_switch_to_no_ffmpeg_window(anime_details)
        episode_page_links = [episode_page_links[eps-anime_details.predicted_episodes_to_download[0]]
                              for eps in anime_details.predicted_episodes_to_download]
        hls_links_progress_bar = ProgressBarWithButtons(
            self, "Retrieving hls links, this may take a while", "", len(episode_page_links), "eps", 1, self.pause_icon, self.resume_icon, self.cancel_icon, lambda: None, lambda: None)
        self.progress_bars_layout.insertWidget(0, hls_links_progress_bar)
        GetHlsLinksThread(self, episode_page_links, anime_details,
                          hls_links_progress_bar, self.hls_get_matched_quality_links).start()

    def hls_get_matched_quality_links(self, anime_details: AnimeDetails, hls_links: list[str]):
        match_progress_bar = ProgressBarWithButtons(
            self, "Matching quality to links", "", len(
                hls_links), "links", 1, self.pause_icon, self.resume_icon, self.cancel_icon, lambda: None, lambda: None
        )
        self.progress_bars_layout.insertWidget(0, match_progress_bar)
        HlsGetMatchedQualityLinkThread(
            self, hls_links, anime_details, match_progress_bar, self.hls_get_segments_urls).start()

    def hls_get_segments_urls(self, anime_details: AnimeDetails, matched_links: list[str]):
        segments_progress_bar = ProgressBarWithButtons(
            self, "Getting segment links", "", len(
                matched_links), "segs", 1, self.pause_icon, self.resume_icon, self.cancel_icon, lambda: None, lambda: None
        )
        self.progress_bars_layout.insertWidget(0, segments_progress_bar)
        HlsGetSegmentsUrlsThread(self, matched_links, anime_details,
                                 segments_progress_bar, self.queue_download).start()

    def get_direct_download_links(self, anime_details: AnimeDetails, download_page_links: list[str], download_info: list[list[str]]):
        direct_download_links_progress_bar = ProgressBarWithButtons(
            self, "Retrieving direct download links, this may take a while", "", len(download_page_links), "eps", 1, self.pause_icon, self.resume_icon, self.cancel_icon, lambda: None, lambda: None)
        self.progress_bars_layout.insertWidget(
            0, direct_download_links_progress_bar)
        GetDirectDownloadLinksThread(self, download_page_links, download_info, anime_details, self.calculate_download_size,
                                     direct_download_links_progress_bar).start()

    def calculate_download_size(self, anime_details: AnimeDetails):
        if anime_details.site == PAHE:
            anime_details.total_download_size = pahe.calculate_total_download_size(
                anime_details.download_info)
            self.queue_download(anime_details)
        elif anime_details.skip_calculating_size:
            self.queue_download(anime_details)
        else:
            calculating_download_size_progress_bar = ProgressBarWithButtons(
                self, "Calculating total download size", "", len(anime_details.ddls_or_segs_urls), "eps", 1, self.pause_icon, self.resume_icon, self.cancel_icon, lambda: None, lambda: None)
            self.progress_bars_layout.insertWidget(
                0, calculating_download_size_progress_bar)
            GogoCalculateDownloadSizes(
                self, anime_details, self.queue_download, calculating_download_size_progress_bar).start()

    def queue_download(self, anime_details: AnimeDetails):
        if not anime_details.anime_folder_path:
            anime_details.anime_folder_path = os.path.join(
                anime_details.default_download_path, anime_details.sanitised_title)
            os.mkdir(anime_details.anime_folder_path)
        if anime_details.is_hls_download:
            total_segments = sum(len(l)
                                 for l in anime_details.ddls_or_segs_urls)
            anime_progress_bar = ProgressBarWithoutButtons(
                self, "Downloading[HLS]", anime_details.anime.title, total_segments, "segs", 1, False)
        elif anime_details.skip_calculating_size:
            anime_progress_bar = ProgressBarWithoutButtons(
                self, "Downloading", anime_details.anime.title, len(anime_details.ddls_or_segs_urls), "eps", 1, False)
        else:
            anime_progress_bar = ProgressBarWithoutButtons(
                self, "Downloading", anime_details.anime.title, anime_details.total_download_size, "MB", 1, False)
        anime_progress_bar.bar.setMinimumHeight(50)

        self.download_queue.add_queued_download(
            anime_details, anime_progress_bar)
        if self.first_download_since_app_start:
            self.downloaded_episode_count = DownloadedEpisodeCount(
                self, 0, anime_details.sanitised_title,
                anime_details.anime_folder_path)

            set_minimum_size_policy(self.downloaded_episode_count)
            self.folder_button = FolderButton(
                cast(str, ''), 100, 100, None)

            def download_is_active() -> bool: return not (self.downloaded_episode_count.is_complete()
                                                          or self.downloaded_episode_count.cancelled)
            self.pause_button = PauseAllButton(download_is_active, self)
            self.cancel_button = CancelAllButton(self)
            set_minimum_size_policy(self.pause_button)
            set_minimum_size_policy(self.cancel_button)
            self.second_row_of_buttons_layout.addWidget(
                self.downloaded_episode_count)
            self.second_row_of_buttons_layout.addSpacerItem(QSpacerItem(50, 0))
            self.second_row_of_buttons_layout.addWidget(self.pause_button)
            self.second_row_of_buttons_layout.addWidget(self.cancel_button)
            self.second_row_of_buttons_layout.addSpacerItem(QSpacerItem(50, 0))
            self.second_row_of_buttons_layout.addWidget(self.folder_button)
            self.second_row_of_buttons_layout.addSpacerItem(QSpacerItem(50, 0))
            self.second_row_of_buttons_layout.addWidget(self.download_queue)
        if not self.pause_button.download_is_active():
            self.start_download()

    def clean_out_previous_download(self):
        if self.first_download_since_app_start:
            self.first_download_since_app_start = False
            return
        self.download_queue.remove_first_queued_download()
        self.first_row_of_progress_bar_layout.removeWidget(
            self.current_anime_progress_bar)
        self.current_anime_progress_bar.deleteLater()
        if self.hls_est_size:
            self.hls_est_size.deleteLater()
            self.hls_est_size = None

    def start_download(self):
        self.clean_out_previous_download()
        current_queued = self.download_queue.get_first_queued_download()
        self.download_queue.remove_buttons_from_queued_download(current_queued)
        anime_details = current_queued.anime_details
        is_hls_download = anime_details.is_hls_download
        if is_hls_download:
            self.hls_est_size = HlsEstimatedSize(
                self, len(anime_details.ddls_or_segs_urls))
            self.second_row_of_buttons_layout.insertWidget(
                0, self.hls_est_size)
        self.current_anime_progress_bar = current_queued.progress_bar
        self.downloaded_episode_count.reinitialise(len(
            anime_details.ddls_or_segs_urls), anime_details.sanitised_title, cast(str, anime_details.anime_folder_path))
        self.first_row_of_progress_bar_layout.addWidget(
            self.current_anime_progress_bar)
        current_download_manager_thread = DownloadManagerThread(
            self, anime_details, self.current_anime_progress_bar, self.downloaded_episode_count)
        self.pause_button.pause_callback = current_download_manager_thread.pause_or_resume
        self.cancel_button.cancel_callback = current_download_manager_thread.cancel
        self.folder_button.folder_path = cast(
            str, anime_details.anime_folder_path)
        current_download_manager_thread.start()

    def make_episode_progress_bar(self, episode_title: str, episode_size_or_segs: int, progress_bars: dict[str, ProgressBarWithButtons], is_hls_download: bool):
        if is_hls_download:
            bar = ProgressBarWithButtons(
                None, "Downloading[HLS]", episode_title, episode_size_or_segs, "segs", 1, self.pause_icon, self.resume_icon, self.cancel_icon, lambda: None, lambda: None)
        else:
            bar = ProgressBarWithButtons(
                None, "Downloading", episode_title, episode_size_or_segs, "MB", IBYTES_TO_MBS_DIVISOR, self.pause_icon, self.resume_icon, self.cancel_icon, lambda: None, lambda: None)
        progress_bars[episode_title] = bar
        self.progress_bars_layout.insertWidget(0, bar)


class DownloadManagerThread(QThread, PausableAndCancellableFunction):
    send_progress_bar_details = pyqtSignal(str, int, dict, bool)
    update_anime_progress_bar_signal = pyqtSignal(int)

    def __init__(self, download_window: DownloadWindow, anime_details: AnimeDetails, anime_progress_bar: ProgressBarWithoutButtons, downloaded_episode_count: DownloadedEpisodeCount) -> None:
        QThread.__init__(self, download_window)
        PausableAndCancellableFunction.__init__(self)
        self.anime_progress_bar = anime_progress_bar
        self.download_window = download_window
        self.downloaded_episode_count = downloaded_episode_count
        self.anime_details = anime_details
        self.update_anime_progress_bar_signal.connect(
            anime_progress_bar.update_bar)
        self.send_progress_bar_details.connect(
            download_window.make_episode_progress_bar)
        self.progress_bars: dict[str, ProgressBarWithButtons] = {}
        self.ongoing_downloads_count = 0
        self.download_slot_available = Event()
        self.download_slot_available.set()
        self.prev_bar = None
        self.mutex = QMutex()
        self.cancelled = False

    def pause_or_resume(self):
        if not self.cancelled:
            for bar in self.progress_bars.values():
                bar.pause_button.click()
            self.anime_progress_bar.pause_or_resume()
        PausableAndCancellableFunction.pause_or_resume(self)

    def cancel(self):
        if self.resume.is_set() and not self.cancelled:
            for bar in self.progress_bars.values():
                bar.cancel_button.click()
            self.downloaded_episode_count.cancelled = True
            self.anime_progress_bar.cancel()
            PausableAndCancellableFunction.cancel(self)

    def update_anime_progress_bar(self, added: int):
        if self.anime_details.is_hls_download:
            self.update_anime_progress_bar_signal.emit(added)
        elif self.anime_details.skip_calculating_size:
            self.update_anime_progress_bar_signal.emit(added)
        else:
            added_rounded = round(added / IBYTES_TO_MBS_DIVISOR)
            self.update_anime_progress_bar_signal.emit(added_rounded)

    def clean_up_finished_download(self, episode_title: str):
        self.progress_bars.pop(episode_title)
        self.ongoing_downloads_count -= 1
        if self.ongoing_downloads_count < cast(int, settings[KEY_MAX_SIMULTANEOUS_DOWNLOADS]):
            self.download_slot_available.set()

    def update_eps_count_and_size(self, is_cancelled: bool, eps_file_path: str):
        hls_est_size = self.download_window.hls_est_size
        if is_cancelled:
            if not self.downloaded_episode_count.cancelled:
                self.downloaded_episode_count.total -= 1
            self.downloaded_episode_count.update_count(0)
            if hls_est_size:
                hls_est_size.update_count(0)
        else:
            self.downloaded_episode_count.update_count(1)
            if hls_est_size:
                eps_size = round(os.path.getsize(
                    eps_file_path) / IBYTES_TO_MBS_DIVISOR)
                hls_est_size.update_count(eps_size)
    # Gogo's direct download link sometimes doesn't work, it returns a 301 - 308 status code meaning the resource has been moved, this attempts to redirect to that link
    # It is applied to Pahe too just in case and to make everything streamlined

    def gogo_check_if_valid_link(self, link: str) -> tuple[str, requests.Response | None]:
        response = CLIENT.get(link, stream=True)
        if response.status_code in RESOURCE_MOVED_STATUS_CODES:
            possible_valid_redirect_link = response.headers.get("location", "")
            return self.gogo_check_if_valid_link(possible_valid_redirect_link) if possible_valid_redirect_link != "" else (link, None)
        try:
            response.headers['content-length']
        except KeyError:
            response = None

        return link, response

    def get_exact_episode_size(self, link: str) -> tuple[str, int]:
        link, response = self.gogo_check_if_valid_link(link)
        return (link, int(response.headers['content-length'])) if response else (link, 0)

    def run(self):
        ddls_or_segs_urls = self.anime_details.ddls_or_segs_urls
        for idx, ddl_or_seg_urls in enumerate(ddls_or_segs_urls):
            self.download_slot_available.wait()
            episode_number = str(
                self.anime_details.predicted_episodes_to_download[idx]).zfill(2)
            episode_title = f"{self.anime_details.sanitised_title} E{episode_number}"
            if self.anime_details.is_hls_download:
                episode_size_or_segs = len(ddl_or_seg_urls)
            else:
                ddl_or_seg_urls, episode_size_or_segs = self.get_exact_episode_size(
                    cast(str, ddl_or_seg_urls))
                if episode_size_or_segs == 0:
                    continue
            # This is specifcally at this point instead of at the top cause of the above http request made in self.get_exact_episode_size such that if a user pauses or cancels as the request is in progress the input will be captured
            self.resume.wait()
            if self.cancelled:
                break
            self.mutex.lock()
            self.send_progress_bar_details.emit(
                episode_title, episode_size_or_segs, self.progress_bars, self.anime_details.is_hls_download)
            self.mutex.unlock()
            while episode_title not in self.progress_bars:
                continue
            episode_progress_bar = self.progress_bars[episode_title]
            DownloadThread(self, ddl_or_seg_urls, episode_title, episode_size_or_segs, self.anime_details.site, self.anime_details.is_hls_download, self.anime_details.skip_calculating_size, self.anime_details.quality, cast(str, self.anime_details.anime_folder_path),
                           episode_progress_bar, self.clean_up_finished_download, self.anime_progress_bar, self.update_anime_progress_bar, self.update_eps_count_and_size, self.mutex).start()
            self.ongoing_downloads_count += 1
            if self.ongoing_downloads_count >= cast(int, settings[KEY_MAX_SIMULTANEOUS_DOWNLOADS]):
                self.download_slot_available.clear()


class DownloadThread(QThread):
    update_bars = pyqtSignal(int)
    finished = pyqtSignal(str)
    update_eps_count_and_hls_sizes = pyqtSignal(bool, str)
    update_bar_if_skipped_calculating_total_size = pyqtSignal(int)

    def __init__(self, parent: DownloadManagerThread, ddl_or_seg_urls: str | list[str], title: str, size: int, site: str, is_hls_download: bool, skipped_calculating_total_download_size: bool, hls_quality: str, download_folder: str,
                 progress_bar: ProgressBarWithButtons, finished_callback: Callable, anime_progress_bar: ProgressBarWithoutButtons, update_anime_progress_bar: Callable, update_eps_count_and_hls_sizes: Callable, mutex: QMutex) -> None:
        super().__init__(parent)
        self.ddl_or_seg_urls = ddl_or_seg_urls
        self.title = title
        self.size = size
        self.download_folder = download_folder
        self.skipped_calculating_total_download_size = skipped_calculating_total_download_size
        self.site = site
        self.hls_quality = hls_quality
        self.is_hls_download = is_hls_download
        self.progress_bar = progress_bar
        self.anime_progress_bar = anime_progress_bar
        self.update_bars.connect(self.progress_bar.update_bar)
        if skipped_calculating_total_download_size:
            self.update_bar_if_skipped_calculating_total_size.connect(
                update_anime_progress_bar)
        else:
            self.update_bars.connect(update_anime_progress_bar)
        self.finished.connect(finished_callback)
        self.update_eps_count_and_hls_sizes.connect(
            update_eps_count_and_hls_sizes)
        self.mutex = mutex
        self.download: Download
        self.is_cancelled = False

    def cancel(self):
        self.download.cancel()
        divisor = 1 if self.is_hls_download else IBYTES_TO_MBS_DIVISOR
        new_maximum = self.anime_progress_bar.bar.maximum() - round(self.size /
                                                                    divisor)
        if new_maximum > 0:
            self.anime_progress_bar.bar.setMaximum(new_maximum)
        new_value = round(self.anime_progress_bar.bar.value(
        ) - round(self.progress_bar.bar.value() / divisor))
        if new_value < 0:
            new_value = 0
        self.anime_progress_bar.bar.setValue(new_value)
        self.is_cancelled = True

    def run(self):
        if self.is_hls_download:
            self.ddl_or_seg_urls = cast(
                list[str], self.ddl_or_seg_urls)
            self.download = Download(
                self.ddl_or_seg_urls, self.title, self.download_folder, lambda x: self.update_bars.emit(x), is_hls_download=True)
        else:
            self.ddl_or_seg_urls = cast(str, self.ddl_or_seg_urls)
            self.download = Download(
                self.ddl_or_seg_urls, self.title, self.download_folder, lambda x: self.update_bars.emit(x))
        self.progress_bar.pause_callback = self.download.pause_or_resume
        self.progress_bar.cancel_callback = self.cancel

        self.download.start_download()
        self.mutex.lock()
        self.finished.emit(self.title)
        if self.skipped_calculating_total_download_size and not self.is_cancelled:
            self.update_bar_if_skipped_calculating_total_size.emit(1)
        self.update_eps_count_and_hls_sizes.emit(
            self.is_cancelled, self.download.file_path)
        self.mutex.unlock()


class GogoGetDownloadPageLinksThread(QThread):
    finished = pyqtSignal(AnimeDetails, list, list)
    hls_finished = pyqtSignal(AnimeDetails, list)

    def __init__(self, download_window: DownloadWindow, anime_details: AnimeDetails, callback: Callable[[AnimeDetails, list[str], list[list[str]]], None] | Callable[[AnimeDetails, list[str]], None]):
        super().__init__(download_window)
        self.anime_details = anime_details
        self.hls_finished.connect(callback)
        self.finished.connect(callback)

    def run(self):
        page_content = gogo.get_anime_page_content(
            self.anime_details.anime.page_link)
        anime_id = gogo.extract_anime_id(page_content)
        episode_page_links = gogo.get_download_page_links(
            self.anime_details.predicted_episodes_to_download[0], self.anime_details.predicted_episodes_to_download[-1], anime_id)
        if self.anime_details.is_hls_download:
            self.hls_finished.emit(self.anime_details, episode_page_links)
        else:
            self.finished.emit(self.anime_details, episode_page_links, [])


class PaheGetTotalPageCountThread(QThread):
    finished = pyqtSignal(AnimeDetails, int)

    def __init__(self, download_window: DownloadWindow, anime_details: AnimeDetails, finished_callback: Callable[[AnimeDetails, int], None]):
        super().__init__(download_window)
        self.anime_details = anime_details
        self.finished.connect(finished_callback)

    def run(self):
        tot_page_count = pahe.get_total_episode_page_count(
            self.anime_details.anime.page_link)
        self.finished.emit(self.anime_details, tot_page_count)


class PaheGetEpisodePageLinksThread(QThread):
    finished = pyqtSignal(AnimeDetails, list)
    update_bar = pyqtSignal(int)

    def __init__(self, parent, anime_details: AnimeDetails, start_episode: int, end_episode: int, finished_callback: Callable[[AnimeDetails, list[str]], None], progress_bar: ProgressBarWithButtons):
        super().__init__(parent)
        self.anime_details = anime_details
        self.finished.connect(finished_callback)
        self.start_episode = start_episode
        self.progress_bar = progress_bar
        self.end_index = end_episode
        self.update_bar.connect(progress_bar.update_bar)

    def run(self):
        obj = pahe.GetEpisodePageLinks()
        self.progress_bar.pause_callback = obj.pause_or_resume
        self.progress_bar.cancel_callback = obj.cancel
        episode_page_links = obj.get_episode_page_links(self.start_episode, self.end_index, self.anime_details.anime.page_link, cast(
            str, self.anime_details.anime.id), lambda x: self.update_bar.emit(x))
        if not obj.cancelled:
            self.finished.emit(self.anime_details, episode_page_links)


class GetHlsLinksThread(QThread):
    finished = pyqtSignal(AnimeDetails, list)
    update_bar = pyqtSignal(int)

    def __init__(self, parent, episode_page_links: list[str], anime_details: AnimeDetails, progress_bar: ProgressBarWithButtons, finished_callback: Callable[[AnimeDetails, list[str]], None]):
        super().__init__(parent)
        self.anime_details = anime_details
        self.episode_page_links = episode_page_links
        self.progress_bar = progress_bar
        self.finished.connect(finished_callback)
        self.update_bar.connect(self.progress_bar.update_bar)

    def run(self):
        obj = gogo.GetHlsLinks()
        self.progress_bar.pause_callback = obj.pause_or_resume
        self.progress_bar.cancel_callback = obj.cancel
        hls_links = obj.get_hls_links(
            self.episode_page_links, self.update_bar.emit)
        if not obj.cancelled:
            self.finished.emit(self.anime_details, hls_links)


class HlsGetMatchedQualityLinkThread(QThread):
    finished = pyqtSignal(AnimeDetails, list)
    update_bar = pyqtSignal(int)

    def __init__(self, parent, hls_links: list[str], anime_details: AnimeDetails, progress_bar: ProgressBarWithButtons, finished_callback: Callable[[AnimeDetails, list[str]], None]):
        super().__init__(parent)
        self.hls_links = hls_links
        self.anime_details = anime_details
        self.progress_bar = progress_bar
        self.finished.connect(finished_callback)
        self.update_bar.connect(self.progress_bar.update_bar)

    def run(self):
        obj = gogo.GetMatchedQualityLinks()
        self.progress_bar.pause_callback = obj.pause_or_resume
        self.progress_bar.cancel_callback = obj.cancel
        matched_links = obj.get_matched_quality_link(
            self.hls_links, self.anime_details.quality, self.update_bar.emit)
        if not obj.cancelled:
            self.finished.emit(self.anime_details, matched_links)


class HlsGetSegmentsUrlsThread(QThread):
    finished = pyqtSignal(AnimeDetails)
    update_bar = pyqtSignal(int)

    def __init__(self, parent, matched_links: list[str], anime_details: AnimeDetails, progress_bar: ProgressBarWithButtons, finished_callback: Callable[[AnimeDetails], None]):
        super().__init__(parent)
        self.matched_links = matched_links
        self.anime_details = anime_details
        self.progress_bar = progress_bar
        self.finished.connect(finished_callback)
        self.update_bar.connect(self.progress_bar.update_bar)

    def run(self):
        obj = gogo.GetSegmentsUrls()
        self.progress_bar.pause_callback = obj.pause_or_resume
        self.progress_bar.cancel_callback = obj.cancel
        self.anime_details.ddls_or_segs_urls = obj.get_segments_urls(
            self.matched_links, self.update_bar.emit)
        if not obj.cancelled:
            self.finished.emit(self.anime_details)


class PaheGetDownloadPageThread(QThread):
    finished = pyqtSignal(AnimeDetails, list, list)
    update_bar = pyqtSignal(int)

    def __init__(self, parent, anime_details: AnimeDetails, episode_page_links: list[str], finished_callback: Callable[[AnimeDetails, list, list], None], progress_bar: ProgressBarWithButtons):
        super().__init__(parent)
        self.anime_details = anime_details
        self.episode_page_links = episode_page_links
        self.finished.connect(finished_callback)
        self.progress_bar = progress_bar
        self.update_bar.connect(progress_bar.update_bar)

    def run(self):
        obj = pahe.GetPahewinDownloadPage()
        self.progress_bar.pause_callback = obj.pause_or_resume
        self.progress_bar.cancel_callback = obj.cancel
        d_page, d_info = obj.get_pahewin_download_page_links_and_info(
            self.episode_page_links, self.update_bar.emit)
        if not obj.cancelled:
            return self.finished.emit(self.anime_details, d_page, d_info)


class GetDirectDownloadLinksThread(QThread):
    finished = pyqtSignal(AnimeDetails)
    update_bar = pyqtSignal(int)

    def __init__(self, download_window: DownloadWindow, download_page_links: list[str] | list[list[str]], download_info: list[list[str]], anime_details: AnimeDetails,
                 finished_callback: Callable[[AnimeDetails], None], progress_bar: ProgressBarWithButtons):
        super().__init__(download_window)
        self.download_window = download_window
        self.download_page_links = download_page_links
        self.download_info = download_info
        self.anime_details = anime_details
        self.finished.connect(finished_callback)
        self.progress_bar = progress_bar
        self.update_bar.connect(progress_bar.update_bar)

    def run(self):
        if self.anime_details.site == PAHE:
            bound_links, bound_info = pahe.bind_sub_or_dub_to_link_info(self.anime_details.sub_or_dub, cast(
                list[list[str]], self.download_page_links), self.download_info)
            bound_links, bound_info = pahe.bind_quality_to_link_info(
                self.anime_details.quality, bound_links, bound_info)
            self.anime_details.download_info = bound_info
            obj = pahe.GetDirectDownloadLinks()
            self.progress_bar.pause_callback = obj.pause_or_resume
            self.progress_bar.cancel_callback = obj.cancel
            self.anime_details.ddls_or_segs_urls = obj.get_direct_download_links(
                bound_links, lambda x: self.update_bar.emit(x))
        else:
            obj = gogo.GetDirectDownloadLinks()
            self.progress_bar.pause_callback = obj.pause_or_resume
            self.progress_bar.cancel_callback = obj.cancel
            self.anime_details.ddls_or_segs_urls = obj.get_direct_download_links(cast(
                list[str], self.download_page_links), self.anime_details.quality, lambda x: self.update_bar.emit(x))

        if not obj.cancelled:
            self.finished.emit(self.anime_details)


class GogoCalculateDownloadSizes(QThread):
    finished = pyqtSignal(AnimeDetails)
    update_bar = pyqtSignal(int)

    def __init__(self, parent: QWidget, anime_details: AnimeDetails, finished_callback: Callable[[AnimeDetails], None], progress_bar: ProgressBarWithButtons):
        super().__init__(parent)
        self.anime_details = anime_details
        self.finished.connect(finished_callback)
        self.progress_bar = progress_bar
        self.update_bar.connect(progress_bar.update_bar)

    def run(self):
        obj = gogo.CalculateTotalDowloadSize()
        self.progress_bar.pause_callback = obj.pause_or_resume
        self.progress_bar.cancel_callback = obj.cancel
        self.anime_details.total_download_size = obj.calculate_total_download_size(
            cast(list[str], self.anime_details.ddls_or_segs_urls), lambda x: self.update_bar.emit(x), True)
        if not obj.cancelled:
            self.finished.emit(self.anime_details)


class AutoDownloadThread(QThread):
    initate_download_pipeline = pyqtSignal(AnimeDetails)
    clean_out_auto_download_thread_signal = pyqtSignal()

    def __init__(self, download_window: DownloadWindow, titles: list[str], tray_icon: QSystemTrayIcon, clean_out_auto_download_thread_slot: Callable[[], None]):
        super().__init__(download_window)
        self.anime_titles = titles
        self.download_window = download_window
        self.initate_download_pipeline.connect(
            self.download_window.initiate_download_pipeline)
        self.tray_icon = tray_icon
        self.clean_out_auto_download_thread_signal.connect(
            clean_out_auto_download_thread_slot)

    def run(self):
        queued: list[str] = []
        for title in self.anime_titles:
            anime: Anime
            site = cast(str, settings[KEY_AUTO_DOWNLOAD_SITE])
            if site == PAHE:
                result = self.pahe_fetch_anime_obj(title)
                if not result:
                    result = self.gogo_fetch_anime_obj(title)
                    if not result:
                        continue
                    site = GOGO
            else:
                result = self.gogo_fetch_anime_obj(title)
                if not result:
                    result = self.pahe_fetch_anime_obj(title)
                    if not result:
                        continue
                    site = PAHE
            anime = result
            anime_details = AnimeDetails(anime, site)
            start_eps = anime_details.haved_end if anime_details.haved_end else 1
            anime_details.predicted_episodes_to_download = dynamic_episodes_predictor_initialiser_pro_turboencapsulator(
                start_eps, anime_details.episode_count, anime_details.haved_episodes)
            if anime_details.predicted_episodes_to_download == []:
                haved_end = anime_details.haved_end
                if anime_details.metadata.airing_status == "FINISHED" and (haved_end and haved_end >= anime_details.episode_count):
                    self.download_window.main_window.settings_window.tracked_anime.remove_anime(
                        anime_details.anime.title)
                    self.download_window.main_window.tray_icon.make_notification(
                        "Finished Tracking", f"You have the final episode of {title} and it has finished airing so I have removed it from your tracking list", True)
                continue
            if anime_details.sub_or_dub == DUB and not anime_details.dub_available:
                self.download_window.main_window.tray_icon.make_notification(
                    "Couldn't find Dub", f"Couldn't find dub for {anime_details.anime.title}", False, None)
                continue
            queued.append(anime_details.anime.title)
            self.initate_download_pipeline.emit(anime_details)
        if queued != []:
            all_str = ', '.join(queued)
            self.download_window.main_window.tray_icon.make_notification(
                "Queued new episodes", all_str, False, self.download_window.main_window.switch_to_download_window)
        self.clean_out_auto_download_thread_signal.emit()

    def pahe_fetch_anime_obj(self, title: str) -> Anime | None:
        results = pahe.search(title)
        for result in results:
            res_title, page_link, anime_id = pahe.extract_anime_title_page_link_and_id(
                result)
            if sanitise_title(res_title.lower(), True) == sanitise_title(title.lower(), True):
                return Anime(title, page_link, anime_id)
        return None

    def gogo_fetch_anime_obj(self, title: str) -> Anime | None:
        results = gogo.search(title)
        for res_title, page_link in results:
            if sanitise_title(res_title.lower(), True) == sanitise_title(title.lower(), True):
                return Anime(title, page_link, None)
        return None
