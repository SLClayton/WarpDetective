import os
import json
from pprint import pprint as pp
from tempfile import gettempdir

import twitter
from twitter.twitter_utils import enf_type
from twitter.error import TwitterError
import instagram_tools

from tools import *
from variables import *
from imaging import getImageFromURL




def getImageFromTweet(twitter_api, tweet, image_position):

    media = getTweetMedia(twitter_api, tweet)

    # Check tweet has enough media slots for this command
    if media is None:
        print("No media found in tweet.")
        return None
    if not 0 < image_position <= len(media):
        print("Tweet media doesn't contain chosen position {}".format(image_position))
        return None

    image_dict = media[image_position - 1]
    url, ext = os.path.splitext(image_dict["media_url_https"])
    large_png_image_url = "{}?format=png&name=4096x4096".format(url)

    image = getImageFromURL(large_png_image_url)
    return image


def getTweetMedia(twitter_api, tweet):
    try:
        return _getTweetMedia(twitter_api, tweet)
    except TwitterError as e:
        print("Twitter error trying to get tweet media from {}".format(tweet.id))
        return _getTweetMedia(getTwitterApi(dev_twitter_login_file), tweet)


def _getTweetMedia(twitter_api, tweet):
    # twitter python api doesnt have a sound method of collecting this so doing hacky way

    url = twitter_api.base_url + "/statuses/show.json?tweet_mode=extended"

    parameters = {
        'id': enf_type('status_id', int, int(tweet.id)),
        'include_entities': enf_type('include_entities', bool, True),
        'include_ext_alt_text': enf_type('include_ext_alt_text', bool, True)
    }

    resp = twitter_api._RequestUrl(url, 'GET', data=parameters)

    data = twitter_api._ParseAndCheckTwitter(resp.content.decode('utf-8'))


    if "extended_entities" in data and "media" in data["extended_entities"]:
        tweet_media = data["extended_entities"]["media"]
    elif "entities" in data and "media" in data["entities"]:
        tweet_media = data["entities"]["media"]
    else:
        tweet_media = None

    return tweet_media


def getTwitterApi(login):

    # If a string is passed, then its filename, get the JSON it refers to.
    if isinstance(login, str):
        with open(login, "r", encoding="utf-8") as f:
            login = json.load(f)


    # Login to twitter
    api = twitter.Api(consumer_key=login["consumer_key"],
                      consumer_secret=login["consumer_secret"],
                      access_token_key=login["access_token_key"],
                      access_token_secret=login["access_token_secret"])

    return api




def getDevTwitterApi():
    return getTwitterApi(dev_twitter_login_file)



def tweet_mentions(tweet, username):
    # Check command tweet mentions this account
    if not any(x for x in tweet.user_mentions if x.screen_name == username):
        print("Tweet doesn't mention @{}".format(username))
        return False
    print("Asserted tweet mentions @{}".format(username))

    return True



def tweetString(tweet):
    s = "{} {} @{}: {}".format(
        datetime.utcfromtimestamp(tweet.created_at_in_seconds).strftime("%Y-%m-%d %H-%M-%S"),
        tweet.id,
        tweet.user.screen_name,
        tweet.text)
    return s


def GetStatusFromAsAccount(status_id, login_file):
    alt_api = getTwitterApi(login_file)

    try:
        tweet = alt_api.GetStatus(status_id=status_id)
        return tweet
    except TwitterError as e:
        print("Error trying to get status on alt account - {}".format(str(e)))
        return None


def getQuoteTweet(twitter_api, tweet):
    if not hasattr(tweet, "quoted_status_id") or tweet.quoted_status_id is None:
        return None
    return getTweet(twitter_api, tweet.quoted_status_id)


def getParentTweet(twitter_api, tweet):
    if not hasattr(tweet, "in_reply_to_status_id") or tweet.in_reply_to_status_id is None:
        return None
    return getTweet(twitter_api, tweet.in_reply_to_status_id)


def getTweet(twitter_api, tweet_id, try_alt=True):
    try:
        return twitter_api.GetStatus(status_id=tweet_id)
    except TwitterError as e:
        if e.message[0]["code"] in [8, 144]:
            print("Attempted to get tweet {} which does not exist.".format(tweet_id))
            return None
        elif e.message[0]["code"] == 136 and try_alt:
            print("Main twitter account blocked from tweet, trying alt.")
            return getTweet(getTwitterApi(dev_twitter_login_file), tweet_id, try_alt=False)
        elif e.message[0]["code"] == 136:
            print("All accounts blocked from accessing tweet {}.".format(tweet_id))

        raise e



def getTweetIsInResponseTo(tweet):
    if hasattr(tweet, "quoted_status_id") and tweet.quoted_status_id is not None:
        target_tweet_id = tweet.quoted_status_id
    elif hasattr(tweet, "in_reply_to_status_id") and tweet.in_reply_to_status_id is not None:
        target_tweet_id = tweet.in_reply_to_status_id
    else:
        target_tweet_id = None

    return target_tweet_id


def getURLs(tweet):
    return [x.expanded_url for x in tweet.urls]


def replyImages(twitter_api, tweet, images, text=""):

    # Save each image as jpg
    image_files = []
    for image in images:
        filename = os.path.join(gettempdir(), "WD_Twitter_{}.jpg".format(os.urandom(6).hex()))
        image.save(filename, format="JPEG", quality=95)
        image_files.append(filename)


    # Split list into batches of 4
    image_batches = shard_list(image_files, 4)
    total_batches = len(image_batches)

    reply_id = tweet.id
    first_tweet = None

    for i, image_batch in enumerate(image_batches):

        tweet_counter = "({}/{})".format(i+1, total_batches)
        if total_batches > 1 and i == 0:
            this_tweet_text = tweet_counter + "\n" + text
        elif total_batches > 1 and i != 0:
            this_tweet_text = tweet_counter
        elif total_batches <= 1 and i == 0:
            this_tweet_text = text
        else:
            this_tweet_text = ""


        tweet = twitter_api.PostUpdate(status=this_tweet_text,
                                       in_reply_to_status_id=reply_id,
                                       media=image_batch,
                                       auto_populate_reply_metadata=True,
                                       verify_status_length=True)
        reply_id = tweet.id

        if i == 0:
            first_tweet = tweet


    for file in image_files:
        os.remove(file)

    return first_tweet


def statusURL(status_id):
    return "https://twitter.com/a/status/{}".format(status_id)


def getAllInstagramPostCodes(tweet):
    possible_post_urls = getURLs(tweet) + tweet.text.split()
    insta_links = [url for url in possible_post_urls if instagram_tools.isInstagramPostLink(url)]
    insta_post_codes = [instagram_tools.getCodeFromURL(url) for url in insta_links]
    insta_post_codes = [x for x in insta_post_codes if x is not None]
    return insta_post_codes




if __name__ == '__main__':
    api = getTwitterApi(dev_twitter_login_file)

    t = getTweet(api, 12988224)