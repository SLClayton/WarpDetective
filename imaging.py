import base64


import boto3
import botocore.config
from PIL import Image

from tools import *
from variables import *

config = botocore.config.Config(read_timeout=900, connect_timeout=300, retries={'max_attempts': 2})
lamd = boto3.client("lambda", config=config)


def getImageFromS3(bucket, s3_key):
    image_bytes = io.BytesIO()
    s3.download_fileobj(Bucket=bucket, Key=s3_key, Fileobj=image_bytes)
    image = Image.open(image_bytes)
    return image


def getImageFromURL(url):
    try:
        request_response = requests.get(url, allow_redirects=True)

        image_bytes = io.BytesIO()
        image_bytes.write(request_response.content)

        image = Image.open(image_bytes)
        return image
    except urllib.error.URLError as e:
        print("urllib error trying to download image - {}".format(e))
        return None


def getFaces(input_image, tweet=None):

    if not isinstance(input_image, Image.Image):
        input_image = Image.open(input_image)

    image = input_image

    # If size is large resize first
    avg_side = avgSide(image)
    max_avg_side = 1800
    if avg_side > max_avg_side:
        print("Image is {}x{} (avg side {}) so resizing to avg side {}.".format(image.width,
                                                                                image.height,
                                                                                avg_side,
                                                                                max_avg_side))
        image = resize_image(image, new_avg_side=max_avg_side)
        avg_side = avgSide(image)


    while True:

        s3_key = "{}/{}{}_{}_im.png".format(s3_images_dir,
                                            datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S"),
                                            "" if tweet is None else "_" + str(tweet.id),
                                            os.urandom(3).hex())

        saveImageToS3(image, s3_bucket, s3_key)

        # Invoke lambda to find faces in s3 file
        print("Invoking {} lambda function on image of size {}x{}".format(lambda_face_detect_func,
                                                                          image.width,
                                                                          image.height))
        r = lamd.invoke(FunctionName=lambda_face_detect_func,
                        InvocationType="RequestResponse",
                        LogType="Tail",
                        Payload=json.dumps({"images": [s3_key]}))

        # Cleanup input image from s3
        s3.delete_object(Bucket=s3_bucket, Key=s3_key)

        # Check amazon lambda worked properly
        amazon_status_code = r["ResponseMetadata"]["HTTPStatusCode"]
        if amazon_status_code != 200:
            print("Lambda response error.")
            print(base64.b64decode(r["ResponseMetadata"]["x-amz-log-result"]))
            return None


        # Check function worked properly
        response = json.loads(r["Payload"].read())


        if ("statusCode" in response and response["statusCode"] == 200 and
            "body" in response and response["body"][s3_key] != "MEMORY_ERROR"):

            boxes = response["body"][s3_key]
            print("Successfully retrieved face positions within image.")
            break

        elif "statusCode" in response and response["statusCode"] != 200:
            print("Status code for find faces is {}\n{}".format(response["statusCode"], json.dumps(response)))
            return None

        elif ("statusCode" not in response or
              (response["statusCode"] == 200 and
               "body" in response and
               response["body"][s3_key] == "MEMORY_ERROR")):

            print("Suspected memory error.")
            pp(response)

            if avg_side < 500:
                print("Suspected Memory error on image below svg side 500.")
                return None
            else:
                avg_side = avg_side * 0.8
                image = resize_image(image, avg_side)
                print("Image size changed to {}x{}".format(image.width, image.height))
                continue

        else:
            print("Unknown face detection error from FD lambda func.")
            pp(response)
            return None





    # Convert each box to what it would be if the original image was used,
    # then use this to crop the faces from the original image.
    faces = []
    for box in boxes:
        fullsize_box = convert_box(box, original_image=image, new_image=input_image)
        face = input_image.crop(fullsize_box)
        faces.append(face)

    return faces


def getHeatmaps(faces):

    # Upload all face images to s3 and collect their keys in a list
    rndstr = os.urandom(3).hex()
    datestr = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")

    raw_s3_keys = []
    for i, face in enumerate(faces):
        s3_key = "{}/{}_{}_face{}.png".format(s3_images_dir, datestr, rndstr, i + 1)
        saveImageToS3(face, s3_bucket, s3_key)
        raw_s3_keys.append(s3_key)

    print("Invoking {} lambda function.".format(lambda_warp_heatmap_func))

    r = lamd.invoke(FunctionName=lambda_warp_heatmap_func,
                    InvocationType="RequestResponse",
                    LogType="Tail",
                    Payload=json.dumps({"images": raw_s3_keys}))

    # Check amazon lambda worked properly
    heatmap_s3_keys = None
    amazon_status_code = r["ResponseMetadata"]["HTTPStatusCode"]
    if amazon_status_code == 200:

        # Check function worked properly
        response = json.loads(r["Payload"].read())
        status_code = response["statusCode"]

        if status_code == 200:
            heatmap_s3_keys = list(response["heatmaps"].values())
            heatmaps = [getImageFromS3(s3_bucket, key) for key in heatmap_s3_keys]

        else:
            print("Error attempting to gen heatmaps for faces.")
            print(json.dumps(response))
            heatmaps = None

    else:
        print("Lambda response error for {} function.".format(lambda_warp_heatmap_func))
        print(base64.b64decode(r["ResponseMetadata"]["x-amz-log-result"]))
        heatmaps = None


    # Cleanup all s3 files not needed anymore
    delete_keys = raw_s3_keys if heatmap_s3_keys is None else raw_s3_keys + heatmap_s3_keys
    try:
        delete_s3_keys(s3_bucket, delete_keys)
    except ClientError as e:
        print("Couldn't delete all keys in s3 - {}".format(e))


    return heatmaps