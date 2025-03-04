from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout
from PyQt6.QtCore import Qt
from windows.main_actual_window import MainWindow, Window
from shared.global_vars_and_funcs import about_bckg_image_path, set_minimum_size_policy, sen_icon_path, morbius_is_peak_icon_path, GITHUB_REPO_URL, gigachad_audio_path, morbius_audio_path, hentai_addict_audio_path
from shared.global_vars_and_funcs import github_icon_path, reddit_icon_path, discord_icon_path, hentai_addict_icon_path, github_sponsors_icon_path, patreon_icon_path, VERSION
from shared.shared_classes_and_widgets import StyledLabel, IconButton, ScrollableSection, AudioPlayer, Icon, Title
from webbrowser import open_new_tab
from sys import platform as sysplatform


class AboutWindow(Window):
    def __init__(self, main_window: MainWindow):
        super().__init__(main_window, about_bckg_image_path)
        main_layout = QVBoxLayout()
        main_widget = ScrollableSection(main_layout)
        reviews_title = Title("Reviews")
        set_minimum_size_policy(reviews_title)
        reviews_widget = QWidget()
        reviews_layout = QHBoxLayout()
        size = 60
        sen_review = Review(Icon(size, size, sen_icon_path), gigachad_audio_path,
                            "SenZmaKi", "69/10 Truly one of the apps of all time.")
        hentai_addict_review = Review(Icon(size, size, hentai_addict_icon_path), hentai_addict_audio_path,
                                      "HentaiAddict01", "0/10 Can't even batch download hentai.. .")
        morbius_is_peak_review = Review(Icon(size, size, morbius_is_peak_icon_path), morbius_audio_path,
                                        "MorbiusIsPeak", "4/10 Morbius better + ratio + morbiusless")
        reviews_layout.addWidget(sen_review)
        reviews_layout.addWidget(hentai_addict_review)
        reviews_layout.addWidget(morbius_is_peak_review)
        reviews_widget.setLayout(reviews_layout)
        set_minimum_size_policy(reviews_widget)
        support_title = Title("Support")
        set_minimum_size_policy(support_title)
        donations_label = StyledLabel()
        donations_label.setText(
            "Konnichiwa 👋🏿 it's Sen, the creator of Senpwai, I'm a goofy ahh ahh college student from Kenya.\nWifi is kinda expensive in my country, so donations help me pay for internet to keep developing new features and fixing bugs")
        set_minimum_size_policy(donations_label)
        github_sponsors_button = IconButton(
            Icon(120, 120, github_sponsors_icon_path), 1.1)
        github_sponsors_button.clicked.connect(lambda: open_new_tab(
            "https://github.com/sponsors/SenZmaKi"))  # type: ignore
        github_sponsors_button.setToolTip(
            "https://github.com/sponsors/SenZmaKi")
        patreon_button = IconButton(Icon(80, 80, patreon_icon_path), 1.1)
        patreon_button.clicked.connect(lambda: open_new_tab(
            "https://patreon.com/Senpwai"))  # type: ignore
        patreon_button.setToolTip("https://patreon.com/Senpwai")
        donation_buttons_widget = QWidget()
        donation_buttons_layout = QHBoxLayout()
        donation_buttons_layout.addWidget(github_sponsors_button)
        donation_buttons_layout.addSpacing(10)
        donation_buttons_layout.addWidget(patreon_button)
        donation_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        donation_buttons_widget.setLayout(donation_buttons_layout)
        leave_a_star_label = StyledLabel()
        leave_a_star_label.setText(
            "You can also support Senpwai by leaving a star on the github repo, stars help other weebs like us know about it")
        set_minimum_size_policy(leave_a_star_label)
        social_links_title = Title("Social Links")
        set_minimum_size_policy(social_links_title)
        bug_reports_label = StyledLabel()
        bug_reports_label.setText(
            "Found a bug or wanna suggest a feature? Report/Suggest it in the discord server, github issues or subreddit")
        set_minimum_size_policy(bug_reports_label)
        github_button = IconButton(Icon(200, 80, github_icon_path), 1.1)
        github_button.clicked.connect(
            lambda: open_new_tab(GITHUB_REPO_URL))  # type: ignore
        github_button.setToolTip(GITHUB_REPO_URL)
        reddit_button = IconButton(Icon(80, 80, reddit_icon_path), 1.1)
        reddit_button.clicked.connect(lambda: open_new_tab(
            "https://reddit.com/r/Senpwai"))  # type: ignore
        reddit_button.setToolTip("https://reddit.com/r/Senpwai")
        discord_button = IconButton(Icon(80, 80, discord_icon_path), 1.1)
        discord_button.clicked.connect(lambda: open_new_tab(
            "https://discord.gg/e9UxkuyDX2"))  # type: ignore
        discord_button.setToolTip("https://discord.gg/e9UxkuyDX2")
        social_links_buttons_widget = QWidget()
        social_links_buttons_layout = QHBoxLayout()
        social_links_buttons_layout.addWidget(github_button)
        social_links_buttons_layout.addSpacing(30)
        social_links_buttons_layout.addWidget(reddit_button)
        social_links_buttons_layout.addSpacing(30)
        social_links_buttons_layout.addWidget(discord_button)
        social_links_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        social_links_buttons_widget.setLayout(social_links_buttons_layout)

        uninstall_title = Title("Uninstall Info")
        set_minimum_size_policy(uninstall_title)
        uninstall_info_label = StyledLabel()
        uninstall_info_label.setText(
            "To completely remove Senpwai (don't know why you would though), post-uninstallation press \"Win + R\",\ntype \"%appdata%\\..\\Local\\Programs\" and press enter. Look for a folder named \"Senpwai\" then delete it")
        set_minimum_size_policy(uninstall_info_label)

        version_title = Title(f"Version {VERSION}")
        set_minimum_size_policy(version_title)

        main_layout.addSpacing(40)
        main_layout.addWidget(reviews_title, Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(reviews_widget, Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(support_title)
        main_layout.addWidget(donations_label)
        main_layout.addWidget(donation_buttons_widget)
        main_layout.addWidget(leave_a_star_label)
        main_layout.addSpacing(40)
        main_layout.addWidget(social_links_title)
        main_layout.addWidget(bug_reports_label)
        main_layout.addWidget(social_links_buttons_widget)
        if sysplatform == "win32":
            main_layout.addWidget(uninstall_title)
            main_layout.addWidget(uninstall_info_label)
        main_layout.addWidget(version_title)
        self.full_layout.addWidget(main_widget, Qt.AlignmentFlag.AlignTop)
        self.setLayout(self.full_layout)


class Review(QWidget):
    def __init__(self, icon: Icon, audio_path: str, author: str, text: str):
        super().__init__()
        main_layout = QVBoxLayout()

        profile_pic = IconButton(icon, 1.1)
        profile_pic.clicked.connect(
            AudioPlayer(self, audio_path, volume=60).play)
        author_name = StyledLabel(None, 15, "orange", font_color="black")
        author_name.setText(author)
        set_minimum_size_policy(author_name)
        review_text = StyledLabel(
            None, 15, font_color="white",  bckg_color="black")
        review_text.setText(text)
        set_minimum_size_policy(review_text)

        main_layout.addWidget(
            profile_pic, alignment=Qt.AlignmentFlag.AlignHCenter)
        main_layout.addWidget(
            author_name, alignment=Qt.AlignmentFlag.AlignHCenter)
        main_layout.addWidget(review_text)
        self.setLayout(main_layout)
        set_minimum_size_policy(self)
