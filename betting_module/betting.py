import os
import traceback
from time import sleep
from datetime import datetime, timedelta
from webdriver_manager.chrome import ChromeDriverManager
from undetected_chromedriver import Chrome, ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from betting_helper import generic_wait, long_wait, balance_check
from betting_match import match_bet
from predicting import (
    predict_match,
    get_unplayed_match_by_team_names,
)
from services.unplayedmatch_service import confirm_bet, set_maps

prediction_threshold = timedelta(minutes=10)

total_balance = None

# service = Service(executable_path=ChromeDriverManager().install())
# service = None
options = ChromeOptions()
options.add_argument("--no-sandbox")
options.add_argument(f"user-data-dir={os.environ['CHROME_PROFILE_DIR']}")
options.add_argument(f"--profile-directory={os.environ['CHROME_PROFILE']}")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-infobars")
options.add_argument("--disable-extensions")
options.add_argument("--disable-gpu")
options.add_argument("--start-fullscreen")

sleep_length = None


def login(browser):
    browser.get("https://thunderpick.io/en/esports?login=true")
    google_ele = generic_wait(browser).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".social-btn--google"))
    )
    google_ele.click()
    sleep(1)
    long_wait(browser).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "div.thp-info-image__icon-container--success")
        )
    )
    generic_wait(browser).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "div.match-group"))
    )


urls_to_skip = []


# number of times to retry betting until favorable odds are found
betting_odds_attempts = 4


def handle_match(bet_url, browser):
    global sleep_length
    browser.get(bet_url)
    match_date = None
    now = datetime.now()
    current_year = str(datetime.now().year)
    try:
        match_date = (
            generic_wait(browser)
            .until(
                EC.presence_of_element_located((By.CLASS_NAME, "match-header__date"))
            )
            .text
        )
        match_date = datetime.strptime(
            current_year + " " + match_date, "%Y %B %d, %H:%M"
        )
    except:
        match_date = now
    if match_date - now > prediction_threshold:
        print(sleep_length)
        if sleep_length == None:
            sleep_length = (match_date - now).total_seconds() - 600
            print("new sleep length", sleep_length)
        # browser.close()
        print("Past threshold, ending until bet at", bet_url)
        raise Exception()
    home_team = (
        generic_wait(browser)
        .until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div.main-market__home-team")
            )
        )
        .text
    )
    away_team = (
        generic_wait(browser)
        .until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div.main-market__away-team")
            )
        )
        .text
    )
    (match, same_order) = get_unplayed_match_by_team_names(
        home_team, away_team, datetime.now()
    )
    # if this match isnt in the database or it has been fully bet on, skip
    if match == None:
        print("No match found for", home_team, away_team)
        urls_to_skip.append(bet_url)
        return
    elif (
        len(
            [
                map_betted
                for map_betted in match["betted"].values()
                if map_betted != None
                and (
                    map_betted["betted_odds"] != None
                    or map_betted.get("try_num", 0) == betting_odds_attempts
                )
            ]
        )
        == match["numMaps"]
    ):
        print("All maps betted for", home_team, away_team)
        urls_to_skip.append(bet_url)
        return
    map_infos = match.get("mapInfos", [])
    if len(map_infos) != match["numMaps"]:
        # do this for edge case that only one map is TBA to prevent adding duplicate maps
        map_infos = []
        browser.get("https://www.hltv.org" + match["matchUrl"])
        print("Page loaded", match["matchUrl"])
        print(
            "wait result",
            WebDriverWait(browser, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.mapholder"))
            ),
        )
        mapholders = browser.find_elements(By.CSS_SELECTOR, "div.mapholder")
        print(len(mapholders), "mapholders found")
        for i, holder in enumerate(mapholders):
            map_name = holder.find_element(By.CSS_SELECTOR, "div.mapname").text
            picked_by = None
            left_picked = (
                len(holder.find_elements(By.CSS_SELECTOR, ".results-left.pick")) == 1
            )
            right_picked = (
                len(holder.find_elements(By.CSS_SELECTOR, ".results-right.pick")) == 1
            )
            if left_picked:
                picked_by = "teamOne"
            elif right_picked:
                picked_by = "teamTwo"
            map_info = {"map_name": map_name, "picked_by": picked_by, "map_num": i}
            print("New map info", map_info)
            map_infos.append(map_info)

        set_maps(
            match["hltvId"],
            [map_info for map_info in map_infos if map_info["map_name"] != "TBA"],
        )
    map_names = list(map(lambda info: info["map_name"], map_infos))
    market_prediction_dict = {}
    if "TBA" in map_names:
        print("Maps still TBA")
        sleep_length = 30
        return
    predictions = predict_match(match, map_infos, same_order)
    print("pred", predictions)
    if len(map_names) == 1:
        market_prediction_dict["Match"] = predictions[map_names[0]]
    else:
        for i in range(len(map_names)):
            market_name = f"Map {i+1} Winner"
            if map_names[i] == "Default":
                confirm_bet(match["hltvId"], {market_name: True})
            if map_names[i] in predictions:
                market_prediction_dict[market_name] = predictions[map_names[i]]
    print(market_prediction_dict, match.get("betted", None))

    # ensures that already betted markets aren't betted again
    market_prediction_dict = {
        k: v
        for k, v in market_prediction_dict.items()
        if not k in match["betted"]
        or match["betted"][k] == None
        or (
            "try_num" in match["betted"][k]
            and match["betted"][k]["try_num"] < betting_odds_attempts
        )
    }

    print(market_prediction_dict)
    print("Trying to bet on", match["title"])

    betted_markets = match_bet(
        market_prediction_dict, bet_url, match["numMaps"], browser
    )
    print("betted_markets", betted_markets)
    for market_name, market_dict in betted_markets.items():
        if market_dict == None:
            sleep_length = 30
        elif market_dict["betted_odds"] == None:
            # if it was not betted due to unfavorable odds, increment tries
            curr_tries = ((match.get("betted", {}).get(market_name, None)) or {}).get(
                "try_num", 0
            )
            print("Current tries", curr_tries)
            betted_markets[market_name]["try_num"] = curr_tries + 1
            sleep_length = min(sleep_length, 60) if sleep_length is not None else 60

    confirm_bet(match["hltvId"], betted_markets)


def make_bets(browser=None):
    global sleep_length
    sleep_length = None
    # options.add_argument("--headless")
    browser.get("https://thunderpick.io/en/esports/csgo")
    try:
        # if this doesn't exist, we aren't signed in
        user_element = generic_wait(browser).until(
            EC.presence_of_element_located((By.CLASS_NAME, "user-summary"))
        )
    except:
        print("Trying to log in...")
        login(browser)
        browser.get("https://thunderpick.io/en/esports/csgo")

    match_sections = list(
        generic_wait(browser).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.match-group"))
        )
    )
    generic_wait(browser).until(balance_check)
    sleep(0.5)
    total_balance = float(
        browser.find_element(By.CSS_SELECTOR, "div.wallet-select__value>span").text
    )

    print(f"[{str(datetime.now())}] Current Balance: $" + str(total_balance))

    match_urls = []

    for match_section in match_sections:
        title = (
            generic_wait(browser)
            .until(
                lambda _: match_section.find_element(By.CLASS_NAME, "match-group-title")
            )
            .text
        )
        if title != "Featured":
            match_urls += list(
                map(
                    lambda link: link.get_attribute("href"),
                    match_section.find_elements(
                        By.CSS_SELECTOR, "a.match-row__total-markets"
                    ),
                )
            )

    match_urls = [url for url in match_urls if not url in urls_to_skip]

    for bet_url in match_urls:
        try:
            handle_match(bet_url, browser)
        except Exception as e:
            break

    # browser.close()


def update_wagers(browser):
    tab_elements = generic_wait(browser).until(
        EC.presence_of_all_elements_located((By.CLASS_NAME, "navbar-main-tabs__tab"))
    )
    wagers_tab = tab_elements[2]
    wagers_tab.click()

    # navbar-main-tabs__tab
    pass


if __name__ == "__main__":
    # named outer_browser to distinguish itself from inner functions' `browser` variables
    outer_browser = Chrome(
        options=options, driver_executable_path=ChromeDriverManager().install()
    )
    # prevents mysterious code hangs sometimes when you do browser.get
    outer_browser.set_page_load_timeout(20)
    while True:
        try:
            # this min makes sure that new betting opportunities are caught if they are added before the next match
            make_bets(outer_browser)
        except Exception as e:
            sleep_length = 60
            print("Error while betting", e)
            print(traceback.format_exc())
        if sleep_length == None:
            sleep_length = 60
        print("Sleeping until", str(datetime.now() + timedelta(seconds=sleep_length)))
        sleep(sleep_length)
