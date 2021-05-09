from datetime import datetime, timedelta
import time
import traceback

import twitter
import boto3
from botocore.session import Session
from botocore.config import Config
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key, Attr

from tools import *
from imaging import *
import instagram_tools
from instagram_tools import isInstagramPostLink
import twitter_tools
from twitter_tools import tweetString, getImageFromTweet, getParentTweet, getQuoteTweet


SUCCESS = "SUCCESS"
NO_MENTION = "NO_MENTION"
NO_COMMAND = "NO_COMMAND"
INSTAGRAM = "INSTAGRAM"
TWITTER = "TWITTER"
IN_PROGRESS = "IN_PROGRESS"
DONE = "DONE"
NOT_IN_PROGRESS = "NOT_IN_PROGRESS"

ddb = boto3.resource("dynamodb")



class TweetProcess:

    def __init__(self, login_file, config, command_tweet_id):
        self.config = config
        self.twitter_api = twitter_tools.getTwitterApi(login_file)
        self.command_tweet = self.twitter_api.GetStatus(status_id=command_tweet_id)

        our_creds = self.twitter_api.VerifyCredentials()
        self.our_handle = our_creds.screen_name
        self.our_id = our_creds.id

        self.log_group = self.config["LOG_GROUP"]
        self.log_stream = self.config["LOG_STREAM"]
        self.min_followers = self.config["MIN_FOLLOWERS"]
        self.min_post_age = timedelta(minutes=self.config["MIN_POST_AGE_MINS"])
        self.min_face_avg_side = self.config["MIN_FACE_AVG_SIDE_PIXELS"]
        self.table_name_twitter = self.config["TABLE_NAME_TWITTER"]
        self.table_name_instagram = self.config["TABLE_NAME_INSTAGRAM"]
        self.mods = self.config["MODS"]
        self.no_faces_msg = self.config["NO_FACES_MSG"]
        self.small_faces_msg = self.config["SMALL_FACES_MSG"]
        self.instagram_reply_msg = self.config["INSTAGRAM_REPLY_MSG"]


        self.twitter_alt_api = None
        self.instagram_api = None
        self.start_time = None

        self.target_type = None
        self.target_media_pos = None
        self.target_tweet = None
        self.target_insta_post = None

        self.post_id = None
        self.primary_key = None
        self.table_name = None
        self.original_image = None
        self.faces = None
        self.heatmaps = None


        self.reply_tweet = None



        print("Setup TweetProcess object for account {} and tweet {}.".format(self.our_handle, self.command_tweet.id))


    def getAltTwitter(self):
        if self.twitter_alt_api is None:
            self.twitter_alt_api = twitter_tools.getDevTwitterApi()
        return self.twitter_alt_api


    def getInstagramApi(self):
        if self.instagram_api is None:
            self.instagram_api = instagram_tools.getAPI()
        return self.instagram_api


    def isMod(self, username):
        return username.lower() in [x.lower() for x in self.mods]


    def getFirstCommandMediaPos(self):
        if self.command_tweet is None:
            print("Command tweet is None")
            return None

        command = None

        hashtags = [h.text for h in self.command_tweet.hashtags]
        for hashtag in hashtags:
            command = getCommand(hashtag)
            if command is not None:
                break

        return command


    def valid_mention(self):
        return twitter_tools.tweet_mentions(self.command_tweet, self.our_handle)


    def target_user_followers(self):
        if self.target_type == INSTAGRAM:
            return self.target_insta_post.followers()
        elif self.target_type == TWITTER:
            return self.target_tweet.user.followers_count
        else:
            print("target type {} is not valid.".format(self.target_type))
            return None


    def target_username(self):
        if self.target_type == INSTAGRAM:
            return self.target_insta_post.username()
        elif self.target_type == TWITTER:
            return self.target_tweet.user.screen_name
        else:
            print("target type {} is not valid.".format(self.target_type))
            return None


    def target_post_age(self):
        now = datetime.utcnow()

        if self.target_type == INSTAGRAM:
            return now - self.target_insta_post.time()

        elif self.target_type == TWITTER:
            tweet_creation_time = datetime.utcfromtimestamp(self.target_tweet.created_at_in_seconds)
            return now - tweet_creation_time

        else:
            print("target type {} is not valid.".format(self.target_type))
            return None


    def saveStatus(self, status_str, message=None):
        now = datetime.utcnow()
        max_len = 2000

        try:

            if self.start_time is None:
                runtime = "(NO STARTTIME)"
            else:
                runtime = now - self.start_time
                runtime = runtime - timedelta(microseconds=runtime.microseconds)

            status_str = status_str.upper()


            replystring = ""
            if self.reply_tweet is not None:
                replystring = " rsp({})".format(str(self.reply_tweet.id))

            targetstring = ""
            if self.target_tweet is not None:
                targetstring = " trg(TW @{}: {} - {})".format(self.target_tweet.user.screen_name,
                                                              self.target_tweet.id,
                                                              self.target_media_pos)

            elif self.target_insta_post is not None:
                targetstring = " trg(IG @{}: {} - {})".format(self.target_insta_post.username(),
                                                              self.target_insta_post.shortcode(),
                                                              self.target_media_pos)


            logstring = "[{}] {} cmd({}: {}){}{}{}".format(
                status_str,
                runtime,
                self.command_tweet.user.screen_name,
                self.command_tweet.id,
                targetstring,
                replystring,
                "" if message is None else ": {}".format(message))

            cw_log(self.log_group, self.log_stream, logstring[:max_len])

            print("Saved log to cloudwatch {}/{}".format(self.log_group, self.log_stream))

        except ClientError as e:
            print("Exception when trying to log something to cloudwatch - {}".format(e))
        except Exception as e:
            error_log_str = "[LOGGING ERROR] exception while forming log - {}".format(str(e))
            cw_log(self.log_group, self.log_stream, error_log_str)


    def mark_post_in_db(self, mark_as):

        try:
            table = ddb.Table(self.table_name)

            if mark_as.upper() == IN_PROGRESS:
                table.put_item(Item={self.primary_key: self.post_id,
                                     "pos": self.target_media_pos})

            elif mark_as.upper() == DONE and self.reply_tweet is not None:
                table.put_item(Item={self.primary_key: self.post_id,
                                     "pos": self.target_media_pos,
                                     "resp_id": self.reply_tweet.id})

            elif mark_as.upper() == NOT_IN_PROGRESS:
                table.delete_item(Key={self.primary_key: self.post_id,
                                       "pos": self.target_media_pos})


            print("Marked post {} image {} as {} in {} db table".format(self.post_id,
                                                                        self.target_media_pos,
                                                                        mark_as.upper(),
                                                                        self.table_name))
        except ClientError as e:
            print("Failed while trying to mark post {} image {} as {} in {} db table".format(self.post_id,
                                                                                             self.target_media_pos,
                                                                                             mark_as.upper(),
                                                                                             self.table_name))


    def get_previous_reply(self):

        print("Checking if {} post {} image {} has been processed before.".format(self.target_type.lower(),
                                                                                  self.post_id,
                                                                                  self.target_media_pos))

        db_table = ddb.Table(self.table_name)
        response = db_table.query(KeyConditionExpression=Key(self.primary_key).eq(self.post_id))

        processed_before = False
        prev_reply_id = None
        for item in response["Items"]:
            if str(self.post_id) == str(item[self.primary_key]) and self.target_media_pos == int(item["pos"]):
                processed_before = True
                if "resp_id" in item:
                    prev_reply_id = item["resp_id"]
                break

        if not processed_before:
            return None

        if prev_reply_id is None:
            return IN_PROGRESS

        try:
            prev_reply = self.twitter_api.GetStatus(status_id=prev_reply_id)
            return prev_reply
        except TwitterError as e:
            return None


    def setInstagramTarget(self, insta_post):
        self.target_type = INSTAGRAM
        self.target_insta_post = insta_post
        self.post_id = self.target_insta_post.shortcode()
        self.table_name = self.table_name_instagram
        self.primary_key = "post_id"


    def setTwitterTarget(self, target_tweet):
        self.target_type = TWITTER
        self.target_tweet = target_tweet
        self.post_id = self.target_tweet.id
        self.table_name = self.table_name_twitter
        self.primary_key = "tweet_id"


    def find_target_media(self):

        quote_tweet = twitter_tools.getQuoteTweet(self.twitter_api, self.command_tweet)

        # Check for target images in quote tweet
        if quote_tweet is not None:
            quote_tweet_media = getImageFromTweet(self.twitter_api, quote_tweet, self.target_media_pos)
            if quote_tweet_media is not None:
                print("Found media in quoted tweet")
                self.setTwitterTarget(quote_tweet)
                return quote_tweet_media


        parent_tweet = getParentTweet(self.twitter_api, self.command_tweet)

        # Check parent tweet for image
        if parent_tweet is not None:
            parent_tweet_media = getImageFromTweet(self.twitter_api, parent_tweet, self.target_media_pos)
            if parent_tweet_media is not None:
                print("Found media in parent tweet")
                self.setTwitterTarget(parent_tweet)
                return parent_tweet_media


        # Collect all insta post codes from links found in tweet, quote tweet and reply tweet
        insta_post_codes = twitter_tools.getAllInstagramPostCodes(self.command_tweet)
        if quote_tweet is not None:
            insta_post_codes += twitter_tools.getAllInstagramPostCodes(quote_tweet)
        if parent_tweet is not None:
            insta_post_codes += twitter_tools.getAllInstagramPostCodes(parent_tweet)


        # Check each code for a possible post and image from chosen media pos
        for post_code in insta_post_codes:
            insta_post = instagram_tools.getPost(post_code, api=self.getInstagramApi())
            if insta_post is not None:
                media = insta_post.getImage(self.target_media_pos)
                if media is not None:
                    print("Found instagram image from link in tweet, quote tweet or parent tweet.")
                    self.setInstagramTarget(insta_post)
                    return media
            time.sleep(0.2)

        return None


    def process_tweet(self, force=False):
        try:
            self._process_tweet(force)
        except Exception as e:
            traceback.print_exc()
            try:
                self.mark_post_in_db(mark_as=NOT_IN_PROGRESS)
            except Exception as e2:
                traceback.print_exc()
                print("Exception while trying to unmark tweet as done - {}".format(traceback.print_exc()))
            msg = traceback.format_exc()
            self.saveStatus("UNKNOWN_ERROR", msg)

            raise e


    def _process_tweet(self, force=False):
        self.start_time = datetime.utcnow()

        print("Processing tweet {}".format(tweetString(self.command_tweet)))


        if not self.valid_mention():
            return

        # Check if command user is a mod and therefore to set force flag as true
        if self.isMod(self.command_tweet.user.screen_name):
            force = True
        if force:
            print("FORCE is ENABLED.")


        # Find if tweet has valid command and what it is
        self.target_media_pos = self.getFirstCommandMediaPos()
        if self.target_media_pos is None:
            print("No valid command in tweet.")
            self.saveStatus("NO_COMMAND")
            return
        print("Found command for media position {} in tweet.".format(self.target_media_pos))


        # Find the target of this command
        self.original_image = self.find_target_media()
        if self.original_image is None:
            print("No target media could be found.")
            self.saveStatus("NO_TARGET")
            return
        if avgSide(self.original_image) < self.min_face_avg_side and not force:
            msg = "{}x{} image size is too small.".format(self.original_image.width, self.original_image.height)
            print(msg)
            self.saveStatus("TINY_IMAGE", msg)
            return
        print("Original {}x{} image retrieved.".format(self.original_image.width, self.original_image.height))



        # Check target owner and post is valid
        if self.target_username().lower() in [self.our_handle, "warpdetective"] and not force:
            print("Command targets Master account")
            self.saveStatus("TARGETS_MASTER", message="The command is targeting this account which isn't allowed.")
            return
        followers = self.target_user_followers()
        if followers < self.min_followers and not force:
            msg = "Post owner only has {} followers (min: {})".format(followers, self.min_followers)
            print(msg)
            self.saveStatus("TOO_FEW_FOLLOWERS", msg)
            return
        print("Enough followers for post owner ({})".format(followers))
        post_age = self.target_post_age()
        if post_age < self.min_post_age and not force:
            msg = "Post is from {} but min post age is {}.".format(post_age, self.min_post_age)
            print(msg)
            self.saveStatus("POST_TOO_NEW", msg)
            return
        print("Target post age is {} which is old enough.".format(post_age))







        # Check DB for a previous reply and respond with a link to it if necessary
        previous_reply = self.get_previous_reply()
        if (isinstance(previous_reply, twitter.models.Status) and
                previous_reply.in_reply_to_user_id != self.command_tweet.id):

            msg = "Target processed before, replying with link to previous reply tweet."
            print(msg)
            prev_tweet_embed_info = self.twitter_api.GetStatusOembed(status_id=previous_reply.id)
            self.reply_tweet = self.twitter_api.PostUpdate(status=prev_tweet_embed_info["url"],
                                                           in_reply_to_status_id=self.command_tweet.id,
                                                           auto_populate_reply_metadata=True,
                                                           verify_status_length=True)
            self.saveStatus("PREV_ANSWER", msg)
            return
        elif (isinstance(previous_reply, twitter.models.Status) and
                previous_reply.in_reply_to_user_id == self.command_tweet.id):

            msg = "Same user has requested this before. Doing nothing."
            print(msg)
            self.saveStatus("PREV_ANSWER_SAME_PERSON", msg)
            return None
        elif previous_reply == IN_PROGRESS:
            msg = "Tweet has been processed but has no response yet."
            print(msg)
            self.saveStatus("REP_CMD_IN_PROG", msg)
            return None
        print("Image not processed before..")


        # Mark this tweet/image as in progress to lock it from duplicates
        self.mark_post_in_db(mark_as=IN_PROGRESS)


        # Find all the faces in the image
        print("Attempting to find faces in image.")
        self.faces = getFaces(self.original_image)
        if self.faces is None:
            msg = "Error getting faces from image. Check Face detection log."
            print(msg)
            self.mark_post_in_db(mark_as=NOT_IN_PROGRESS)
            self.saveStatus("FACE_DET_ERROR", msg)
            return
        elif len(self.faces) == 0 and not force:
            print("No faces found in image.")
            self.reply_tweet = self.twitter_api.PostUpdate(status=self.no_faces_msg,
                                                           in_reply_to_status_id=self.command_tweet.id,
                                                           auto_populate_reply_metadata=True,
                                                           verify_status_length=True)
            self.mark_post_in_db(mark_as=DONE)
            self.saveStatus("SUCCESS_NO_FACES")
            return
        print("Found {} faces in image.".format(len(self.faces)))


        # Filter for faces above resolution minimum
        self.faces = [x for x in self.faces if avgSide(x) > self.min_face_avg_side]
        if len(self.faces) == 0 and not force:
            print("No faces over avg side {} in image.".format(self.min_face_avg_side))
            self.reply_tweet = self.twitter_api.PostUpdate(status=self.small_faces_msg,
                                                           in_reply_to_status_id=self.command_tweet.id,
                                                           auto_populate_reply_metadata=True,
                                                           verify_status_length=True)
            self.mark_post_in_db(mark_as=DONE)
            self.saveStatus("SUCCESS_SMALL_FACES")
            return

        print("Found {} faces with avg side length, at least {}".format(len(self.faces), self.min_face_avg_side))


        # Get heatmaps from faces
        try:
            self.heatmaps = getHeatmaps(self.faces)
        except Exception as e:
            print("Error getting heatmaps")
            self.saveStatus("HEATMAP_GEN_ERROR", message=str(e))
            self.mark_post_in_db(mark_as=NOT_IN_PROGRESS)
            return
        if self.heatmaps is None:
            self.mark_post_in_db(mark_as=NOT_IN_PROGRESS)
            self.saveStatus("HEATMAP_GEN_ERROR_RESP")
            return
        print("{} face heatmaps generated and downloaded.".format(len(self.heatmaps)))

        if len(self.heatmaps) < 1:
            print("No heatmaps found in image.")
            self.mark_post_in_db(mark_as=NOT_IN_PROGRESS)
            self.saveStatus("NO_HEATMAPS", message="Heatmap func returned nothing, this shouldn't happen ever.")
            return



        # Tweet back the images to the main command tweet
        text = ""
        tweet_images = self.heatmaps
        if self.target_type == INSTAGRAM:
            text = "{1}\nFirst image is original.\n{0}"\
                .format(self.instagram_reply_msg,
                        self.target_insta_post.tweetString())

            tweet_images.insert(0, self.original_image)
        try:
            self.reply_tweet = twitter_tools.replyImages(self.twitter_api,
                                                         self.command_tweet,
                                                         self.heatmaps,
                                                         text=text)
        except Exception as e:
            print("Error trying to reply tweet to {}".format(self.command_tweet.id))
            self.mark_post_in_db(mark_as=NOT_IN_PROGRESS)
            self.saveStatus("TWEETING_ERROR", message=str(e))
            return
        print("Tweeted reply to original command tweet: {}".format(self.reply_tweet.id))


        # Mark as success in DB
        self.mark_post_in_db(mark_as=DONE)
        self.saveStatus("SUCCESS")





if __name__ == '__main__':
    pass