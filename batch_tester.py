import os
import traceback
from pprint import pprint as pp
import time
import random
import csv

import instagram_tools
import twitter_tools
import twitter
from imaging import getFaces, getHeatmaps
from tools import *


root_dir = r"C:\Users\saman\Desktop\WD_test_twitter"
raw_dir = os.path.join(root_dir, "raw")
usernames_file = os.path.join(root_dir, "usernames.txt")
done_usernames_file = os.path.join(root_dir, "done_usernames.txt")
good_heatmaps_dir = os.path.join(root_dir, "good_heatmaps")

account_name = "WarpDetective"

output_dir = r"C:\Users\saman\Desktop\WD_test\raw"

max_codes = 40



def process_code(shortcode, api=None):
    if api is None:
        api = instagram_tools.getAPI()

    print("SC: {}".format(shortcode))
    post = instagram_tools.getPost(shortcode)
    print("Found post " + str(post))

    images = []
    for i in range(1, 100):
        image = post.getImage(i)
        if image is None:
            break
        images.append(image)

    if len(images) < 1:
        print("No images found for post " + shortcode)
        return

    print("Found {} images in this post.".format(len(images)))

    for i, image in enumerate(images):
        filename = "{}_img{}.png".format(shortcode, i+1)
        filepath = os.path.join(output_dir, filename)
        image.save(filepath, format="PNG")
        print("Saved {}".format(filename))


def list_good_heatmaps_instagram():

    filenames = [f for f in os.listdir(good_heatmaps_dir) if os.path.isfile(os.path.join(good_heatmaps_dir, f))]
    images_todo = []
    for f in filenames:
        code = f[0:11]
        image = f.split("_")[-2][-1]
        face = f[-5]
        images_todo.append({"code": code, "image": int(image)})

    return images_todo


def list_good_heatmaps_twitter():

    filenames = [f for f in os.listdir(good_heatmaps_dir) if os.path.isfile(os.path.join(good_heatmaps_dir, f))]
    images_todo = []
    for f in filenames:

        filename_no_ext = os.path.splitext(f)[0]
        print("Trying {}".format(filename_no_ext))
        tweet_id, image_number, face_number = filename_no_ext.split("_")

        # Avoid duplicates
        for i in images_todo:
            if i["tweet_id"] == tweet_id and i["image_number"] == image_number:
                continue

        images_todo.append({"tweet_id": tweet_id, "image_number": int(image_number)})

    return images_todo







def make_tweet_text_insta(code, image, account):
    words = ["@{}".format(account), "#check{}".format(image), instagram_tools.getURLFromCode(code)]
    random.shuffle(words)
    return " ".join(words)

def make_tweet_text_twitter(tweet_id, image, account):
    words = ["@{}".format(account), "#check{}".format(image)]
    random.shuffle(words)
    words.insert(0, twitter_tools.statusURL(tweet_id))
    return " ".join(words)


def createCSV(tweet_texts, output_filepath):
    with open(output_filepath, "w", newline="") as csvfile:
        filewriter = csv.writer(csvfile, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)

        filewriter.writerow(["Message", "Post URL", "Image URL"])
        for text in tweet_texts:
            filewriter.writerow([text])


def CSVFromHeatmaps_instagram():

    posts = list_good_heatmaps_instagram()
    texts = [make_tweet_text_insta(c["code"], c["image"], "WarpDetective") for c in posts]

    half = int(len(texts) / 2)
    createCSV(texts[:half], os.path.join(root_dir, "tweet_schedule1.csv"))
    createCSV(texts[half:], os.path.join(root_dir, "tweet_schedule2.csv"))


def CSVFromHeatmaps_twitter():

    posts = list_good_heatmaps_twitter()
    texts = [make_tweet_text_twitter(c["tweet_id"], c["image_number"], account_name) for c in posts]

    half = int(len(texts) / 2)
    createCSV(texts[:half], os.path.join(root_dir, "tweet_schedule1.csv"))
    createCSV(texts[half:], os.path.join(root_dir, "tweet_schedule2.csv"))


def downloadTwitterUserImages(since_time):

    usernames = sorted(list(set(getList(usernames_file))))
    saveList(usernames, usernames_file)
    print("Found {} usernames in list: {}".format(len(usernames), usernames))

    api = twitter_tools.getTwitterApi(r"logins\test_twitter_login.json")

    done_usernames = []

    while len(usernames) > 0:

        try:
            username = usernames[0]
            print("\n\nUsing user @{}".format(username))


            tweets = api.GetUserTimeline(screen_name=username,
                                         count=1000,
                                         include_rts=False,
                                         exclude_replies=True)

            tweets = [t for t in tweets if datetime.utcfromtimestamp(t.created_at_in_seconds) > since_time]
            print("Found {} tweets since {}".format(len(tweets), since_time))

            for tweet in tweets:
                for i in range(1, 5):

                    try:
                        image = twitter_tools.getImageFromTweet(api, tweet, i)
                    except twitter.error.TwitterError:
                        time.sleep(60)
                        image = twitter_tools.getImageFromTweet(api, tweet, i)

                    if image ==  None:
                        break
                    filepath = os.path.join(raw_dir, "{}_{}.png".format(tweet.id, i))
                    image.save(filepath, "PNG")
                    print("Saved image to {}".format(filepath))

        except Exception as e:
            traceback.print_exc()
            continue


        done_usernames.append(username)
        done_usernames.sort()
        saveList(done_usernames, done_usernames_file)
        usernames.pop(0)
        saveList(usernames, usernames_file)


    print("\n\nCOMPLETE")




if __name__ == '__main__':

    downloadTwitterUserImages(datetime(2020, 12, 1))




