import requests
from pprint import pprint as pp
import re

import random
import time

#from instagram_web_api import Client, ClientCompatPatch, ClientError, ClientLoginError, ClientCookieExpiredError
from instagram_private_api import Client, ClientCookieExpiredError, ClientLoginError


from imaging import *


user_id = "17841435542350489"




class InstagramPost:

    def __init__(self, post_data, api):
        self.post_data = post_data
        self.api = api
        self.user_data = None

    def shortcode(self):
        try:
            return self.post_data["code"]
        except KeyError or TypeError as e:
            print("Couldnt find shortcode for insta post.")
            return None

    def username(self):
        try:
            return self.post_data["user"]["username"]
        except KeyError or TypeError as e:
            return None

    def user_id(self):
        return self.post_data["user"]["pk"]

    def followers(self):
        if self.user_data is None:
            time.sleep(0.4)
            self.user_data = self.api.user_info(self.user_id())["user"]

        return self.user_data["follower_count"]

    def getImage(self, position):

        if "carousel_media" in self.post_data:
            media_items = [x["image_versions2"] for x in self.post_data["carousel_media"]]
        elif "image_versions2" in self.post_data:
            media_items = [self.post_data["image_versions2"]]
        else:
            pp(self.post_data)
            raise Exception("Could not find images in instagram post data.")


        if not (0 < position <= len(media_items)):
            print("Looking for media in position {} but there's {} media items".format(position, len(media_items)))
            return None


        image_sizes = media_items[position-1]
        largest_size_candidate = sorted(image_sizes["candidates"], key=lambda k: k["width"])[-1]
        image_url = largest_size_candidate["url"]
        image = getImageFromURL(image_url)

        return image


    def id(self):
        return self.post_data["pk"]


    def time(self):
        timestamp_seconds = self.post_data["taken_at"]
        dt = datetime.utcfromtimestamp(timestamp_seconds)
        return dt


    def caption(self):
        try:
            return self.post_data["caption"]["text"]
        except KeyError:
            return None
        except TypeError:
            return None


    def __str__(self):
        s = "{} {} @{}: \"{}\"".format(self.time(),
                                     self.shortcode(),
                                     self.username(),
                                     self.caption().replace("\n", " "))
        return s

    def __repr__(self):
        return self.__str__()


    def tweetString(self):
        s = "IG: {} posted on {} {}".format(self.username(),
                                            self.time().day,
                                            self.time().strftime("%b %Y"))
        return s


def getPost(shortcode, api=None):
    if api is None:
        api = getAPI()

    post_data = getPostData(shortcode, api)
    if post_data is None:
        return None

    return InstagramPost(post_data, api)



def isInstagramPostLink(string):
    link_pattern = re.compile("^(?:https?:/{0,2})?(?:www\\.)?instagram.com/p/[a-zA-Z0-9\\-_]{5,}/?(?:\\?.*)?$")
    return link_pattern.match(string) is not None


def getCodeFromURL(url):
    url = url.strip()
    pattern = re.compile("instagram.com/p/[a-zA-Z0-9\\-_]{5,}(?:$|/|\\?)")
    match = pattern.search(url)

    if match is None:
        print("URL '{}' was not recognised as a valid insta post URL.".format(url))
        return None

    matched = match.group()

    if matched.endswith("?") or matched.endswith("/"):
        matched = matched[:-1]

    code = matched[len("instagram.com/p/"):]

    return code


def getURLFromCode(code):
    return "https://www.instagram.com/p/{}/".format(code)


def saveSettingsToS3(api):
    json_string = json.dumps(dictBytes2B64(api.settings))
    s3_key = "config/instagram_settings_{}.json".format(api.username)
    saveTextToS3(json_string, s3_bucket, s3_key)


def getSettingsFromS3(username):
    s3_key = "config/instagram_settings_{}.json".format(username)
    json_string = getTextFroms3(s3_bucket, s3_key)
    if json_string is None:
        return None
    dict_b64 = json.loads(json_string)
    dict_bytes = dictB642Bytes(dict_b64)
    return dict_bytes


def getAPI(refresh=False):
    print("Getting instagram API.")
    api = None

    # Get accounts info from s3 and shuffle them randomly
    accounts = json.loads(getTextFroms3(s3_bucket, instagram_accounts_key))
    usernames = list(accounts.keys())
    random.shuffle(usernames)

    # Try logging into instagram with each key
    for username in usernames:
        password = accounts[username]

        print("Attempting to get instagram api for account '{}'".format(username))

        settings = getSettingsFromS3(username)
        if settings is None:
            print("Could not find instagram settings in s3.")
            refresh = True
        else:
            print("Found previous instagram login settings in s3")

        if not refresh:
            try:
                api = Client(username=username,
                             password=password,
                             settings=settings)
            except ClientCookieExpiredError or ClientLoginError as e:
                print("Error logging into instagram using existing settings - {}".format(e))
                refresh = True

        if refresh:
            print("Re-logging-in to instagram.")

            try:
                api = Client(username=username,
                             password=password)
            except Exception as e:
                print("Could not fresh login as {}.".format(username))
                continue

            print("Saving new api settings in s3.")
            saveSettingsToS3(api)


        print("Logged into instagram as {} - {}".format(api.authenticated_user_name, api.authenticated_user_id))

        return api

    print("Unable to login with any of the usernames " + str(usernames))
    return None


def media_id_to_code(media_id):
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    short_code = ''
    while media_id > 0:
        remainder = media_id % 64
        media_id = (media_id-remainder)/64
        short_code = alphabet[remainder] + short_code
    return short_code


def code_to_media_id(short_code):
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
    media_id = 0;
    for letter in short_code:
        media_id = (media_id*64) + alphabet.index(letter)

    return media_id


def getPostData(shortcode, api=None):
    if api is None:
        api = getAPI()

    print("Attempting to get post data for instagram post {}".format(shortcode))
    media_id = code_to_media_id(shortcode)

    try:
        response = api.media_info(media_id)
        return response["items"][0]
    except Exception as e:
        print("Error getting post data for instagram code {} - {}".format(shortcode, str(e)))
        return None


def insta_test(shortcode, position=1):
    p = getPost(shortcode)
    img = p.getImage(position)
    faces = getFaces(img)
    if len(faces) < 1:
        print("No faces")
        return
    heatmaps = getHeatmaps(faces)
    for i, hm in enumerate(heatmaps):
        hm.save("insta_test_hm{}.jpg".format(i+1))
    print("Done.")


def get_user_feed_codes(username, amount, api=None):
    if api is None:
        api = getAPI()

    user_id = username2userid(username, api)
    if user_id is None:
        return None


    max_id = None
    codes = []
    while True:
        r = api.user_feed(user_id=user_id, max_id=max_id)
        new_codes = [x["code"] for x in r["items"]]
        codes += new_codes
        max_id = r["next_max_id"] if "next_max_id" in r else None

        if max_id is None or len(new_codes) == 0 or len(codes) >= amount:
            break

    return codes[:amount]


def username2userid(username, api=None):
    if api is None:
        api = getAPI()

    r = api.search_users(username)
    for user in r["users"]:
        if "username" in user and user["username"] == username:
            return user["pk"]

    return None



if __name__ == '__main__':
    api = getAPI()



    

