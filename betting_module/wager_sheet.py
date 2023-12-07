import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from services.wager_service import get_all_finished_wagers
from services.unplayedmatch_service import get_match_url_by_id, get_match_title_by_id

# If modifying these scopes, delete the file token.json.
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# The ID and range of a sample spreadsheet.
SPREADSHEET_ID = "1wCcFA2dFe8rGpv0NUdCsN7w4ywBjoADn0wRIU8qXWw8"
COLUMN_RANGE = "A1:E1"

TOKEN_PATH = "google_token.json"
CREDENTIAL_PATH = "google_credentials.json"


def write_wagers(wagers):
    """Shows basic usage of the Sheets API.
    Prints values from a sample spreadsheet.
    """

    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIAL_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())

    try:
        service = build("sheets", "v4", credentials=creds)

        wager_range = []
        for wager in wagers:
            wager_link = get_match_url_by_id(wager["matchId"])
            wager_title = get_match_title_by_id(wager["matchId"]) + (
                f"- {wager['marketName']}" if "marketName" in wager else ""
            )

            link_formula = f'=HYPERLINK("{wager_link}","{wager_title}")'
            wager_range.append(
                [
                    wager.get("creationDate").strftime("%Y-%m-%d %H:%M:%S.%f")
                    if "creationDate" in wager
                    else "",
                    link_formula,
                    wager["amountBetted"],
                    wager["odds"],
                    wager.get("result", "UNFINISHED"),
                ]
            )
        body = {"values": wager_range}

        # Call the Sheets API
        sheet = (
            service.spreadsheets()
            .batchUpdate(
                spreadsheetId=SPREADSHEET_ID,
                body={
                    "requests": [
                        {
                            "insertDimension": {
                                "range": {
                                    "sheetId": 0,
                                    "dimension": "ROWS",
                                    "startIndex": 2,
                                    "endIndex": 2 + len(wagers),
                                },
                                # "inheritFromBefore": True,
                            }
                        }
                    ]
                },
            )
            .execute()
        )
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=COLUMN_RANGE,
            # insertDataOption="INSERT_ROWS",
            valueInputOption="USER_ENTERED",
            body=body,
        ).execute()
        # values = result.get("values", [])

    except HttpError as err:
        print(err)


if __name__ == "__main__":
    all_wagers = list(get_all_finished_wagers())
    # print(len(all_wagers))
    write_wagers(all_wagers)
