import pymongo
import os
from time import sleep
from datetime import datetime, timedelta
from webdriver_manager.chrome import ChromeDriverManager

from selenium.webdriver import Chrome, ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.core.utils import ChromeType
from pyvirtualdisplay import Display

from predicting import predict_match, confirm_bet


prediction_threshold = timedelta(minutes=10)
bet_percent = 0.05
small_bet_percent = 0.01


service = Service(executable_path=ChromeDriverManager().install())
options = ChromeOptions()
# options.add_argument("--no-sandbox")
options.add_argument(f"user-data-dir={os.environ['CHROME_PROFILE_DIR']}")
options.add_argument(f"--profile-directory={os.environ['CHROME_PROFILE']}")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-extensions")


def login(browser):
    # login_ele = browser.find_element(By.CSS_SELECTOR, ".auth-menu__login-button > a")
    # login_ele.click()
    browser.get("https://thunderpick.io/en/esports?login=true")
    google_ele = browser.find_element(By.CSS_SELECTOR, ".social-btn--google")
    google_ele.click()


urls_to_skip = []


def make_bets():
    sleep_length = None
    # options.add_argument("--headless")
    browser = Chrome(service=service, options=options)
    browser.get("https://thunderpick.io/en/esports/csgo")
    # if this doesn't exist, we aren't signed in
    try:
        user_element = browser.find_element(By.CLASS_NAME, "user-summary")
    except:
        print("Trying to log in...")
        # login(browser)

    now = datetime.now()
    current_year = str(datetime.now().year)
    sleep(0.5)
    browser.implicitly_wait(10)
    total_balance = float(
        browser.find_element(By.CSS_SELECTOR, "div.wallet-select__value>span").text
    )

    print("Balance: $" + str(total_balance))

    match_urls = list(
        map(
            lambda link: link.get_attribute("href"),
            browser.find_elements(By.CSS_SELECTOR, "a.match-row__total-markets"),
        )
    )
    match_urls = [url for url in match_urls if not url in urls_to_skip]

    for bet_url in match_urls:
        browser.get(bet_url)
        match_date = None
        try:
            match_date = (
                WebDriverWait(browser, 10)
                .until(
                    EC.presence_of_element_located(
                        (By.CLASS_NAME, "match-header__date")
                    )
                )
                .text
            )
            match_date = datetime.strptime(
                current_year + " " + match_date, "%Y %B %d, %H:%M"
            )
        except:
            match_date = now
        if match_date - now > prediction_threshold:
            print("Past threshold, ending.")
            if sleep_length == None:
                sleep_length = (match_date - now).total_seconds() - 600
            browser.close()
            return sleep_length
        home_team = (
            WebDriverWait(browser, 10)
            .until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.main-market__home-team")
                )
            )
            .text
        )
        away_team = (
            WebDriverWait(browser, 10)
            .until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "div.main-market__away-team")
                )
            )
            .text
        )
        (predictions, match) = predict_match(home_team, away_team)
        if match == None or len(match["betted"]) == match["numMaps"]:
            urls_to_skip.append(bet_url)
            continue
        browser.get("https://www.hltv.org" + match["matchUrl"])
        map_names = list(
            map(
                lambda map_ele: map_ele.text,
                browser.find_elements(
                    By.CSS_SELECTOR, "div.map-name-holder > div.mapname"
                ),
            ),
        )
        browser.get(bet_url)
        market_elements = WebDriverWait(browser, 10).until(
            EC.presence_of_all_elements_located(
                (
                    By.CSS_SELECTOR,
                    "div.infinite-scroll-list > .market-accordion",
                )
            )
        )
        sleep(0.5)
        for market_element in market_elements:
            market_title = (
                WebDriverWait(browser, 10)
                .until(
                    EC.presence_of_element_located(
                        (By.CLASS_NAME, "market-accordion__market-name")
                    )
                )
                .text
            )
            for i in range(1, 4):
                if market_title == f"Map {i} Winner" and not i in match["betted"]:
                    home_button = market_element.find_element(
                        By.CSS_SELECTOR, "button.odds-button--home-type"
                    )
                    try:
                        home_odds = (
                            float(
                                home_button.find_element(
                                    By.CSS_SELECTOR, "span.odds-button__odds"
                                ).text
                            )
                            - 1
                        )
                    except:
                        # in this case, the betting is locked and we haven't yet been able to bet on it, so we set the returned sleep length to this
                        sleep_length = 60
                        continue
                    away_button = market_element.find_element(
                        By.CSS_SELECTOR, "button.odds-button--away-type"
                    )
                    away_odds = (
                        float(
                            away_button.find_element(
                                By.CSS_SELECTOR, "span.odds-button__odds"
                            ).text
                        )
                        - 1
                    )
                    total_odds = home_odds + away_odds
                    # counterintuitive, but for example if away odds are 12, we want new home odds to be high, not new away odds
                    home_odds = away_odds / total_odds
                    away_odds = home_odds / total_odds
                    curr_map = map_names[i - 1]
                    if curr_map != "TBA":
                        # browser.execute_script(
                        #     "scroll(0,arguments[0])", away_button.rect["y"]
                        # )
                        home_win = False
                        if (
                            predictions[curr_map][0] >= 0.4
                            and predictions[curr_map][0] >= home_odds
                        ):
                            home_win = True
                            home_button.click()
                        elif (
                            predictions[curr_map][1] >= 0.4
                            and predictions[curr_map][1] >= away_odds
                        ):
                            away_button.click()
                        try:
                            pending_bet_input = WebDriverWait(browser, 10).until(
                                EC.presence_of_element_located(
                                    (
                                        By.CSS_SELECTOR,
                                        "div.selections-list input.thp-input",
                                    )
                                )
                            )
                            amount_to_bet = total_balance * (
                                bet_percent
                                if (
                                    (home_win and predictions[curr_map][0] >= 0.6)
                                    or (
                                        not home_win and predictions[curr_map][1] >= 0.6
                                    )
                                )
                                else small_bet_percent
                            )
                            pending_bet_input.send_keys(amount_to_bet)
                            submit_button = browser.find_element(
                                By.CLASS_NAME, "bet-slip__floating-button"
                            )
                            submit_button.click()
                            WebDriverWait(browser, 10).until(
                                EC.none_of(
                                    EC.presence_of_element_located(
                                        (
                                            By.CSS_SELECTOR,
                                            "div.selections-list input.thp-input",
                                        )
                                    )
                                )
                            )
                            confirm_bet(match["hltvId"], i)

                        except:
                            close_buttons = browser.find_elements(
                                By.CLASS_NAME, "selection-header__close-button"
                            )
                            for button in close_buttons:
                                button.click()
                            print(f"No bet made on map {i}")

    browser.close()
    return sleep_length


while True:
    sleep_length = 60
    try:
        sleep_length = make_bets()
    except Exception as e:
        print("Error while betting", e)
    sleep(sleep_length)
