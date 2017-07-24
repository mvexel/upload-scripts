import os
from appJar import gui
from rauth import OAuth1Service
from http import cookiejar
import urllib
import sys
import requests
import webbrowser
import exifread
from operator import itemgetter


TITLE = "OpenStreetCam Upload"
INSTRUCTIONS = """With this application, you can upload a directory of photos to OpenStreetCam.
This can be a directory copied from the OSC app on your phone, or a directory of photos with EXIF location data from for example an action camera."""

upload_dir = None
authorize_url = None
osm = None
request_token = None
request_token_secret = None

url_sequence = 'http://openstreetcam.com/1.0/sequence/'
url_photo = 'http://openstreetcam.com/1.0/photo/'
url_finish = 'http://openstreetcam.com/1.0/sequence/finished-uploading/'
url_access = 'http://openstreetcam.com/auth/openstreetmap/client_auth'

uploadTypes = {
    "app": "Directory copied from OSC app",
    "exif": "Directory of photos with EXIF location"
}


def pickDirectory(val):
    global upload_dir
    upload_dir = app.directoryBox("Directory", os.path.expanduser("~"))
    app.setMessage("dirname", upload_dir)
    scanSourceFolder()


def doUpload(val):
    if not upload_dir:
        app.infoBox("No Directory Selected", "You didn't select a directory to upload yet")


def hasToken():
    return os.path.isfile('access_token.txt')


def getRequestTokens(val):
    # determine input read method
    global authorize_url
    global osm
    global request_token
    global request_token_secret

    osm = OAuth1Service(
        name='openstreetmap',
        consumer_key='rBWV8Eaottv44tXfdLofdNvVemHOL62Lsutpb9tw',
        consumer_secret='rpmeZIp49sEjjcz91X9dsY0vD1PpEduixuPy8T6S',
        request_token_url='http://www.openstreetmap.org/oauth/request_token',
        access_token_url='http://www.openstreetmap.org/oauth/access_token',
        authorize_url='http://www.openstreetmap.org/oauth/authorize',
        signature_obj='',
        base_url='http://www.openstreetmap.org/')

    request_token, request_token_secret = osm.get_request_token()
    authorize_url = osm.get_authorize_url(request_token)

    # Open browser to let user grant access and store token
    webbrowser.open(authorize_url)
    app.setMessage("okOAuthStep1", "OK")
    app.setButtonState("Get Request Token", "disabled")


def GetAccessToken(val):

    if not request_token and request_token_secret:
        app.infoBox("Get Tokens First", "Please Get Request Tokens before getting Access Tokens.")

    cj = cookiejar.CookieJar()
    cookies = [{
        "name": "",
        "value": "",
        "domain": "domain",
        "path": "path",
        "secure": "secure",
    }]
    for cookie in cookies:
        c = cookiejar.Cookie(version=1,
                             name=cookie["name"],
                             value=cookie["value"],
                             port=None,
                             port_specified=False,
                             domain=cookie["domain"],
                             domain_specified=False,
                             domain_initial_dot=False,
                             path=cookie["path"],
                             path_specified=True,
                             secure=cookie["secure"],
                             expires=None,
                             discard=True,
                             comment=None,
                             comment_url=None,
                             rest={'HttpOnly': None},
                             rfc2109=False)
        cj.set_cookie(c)
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cj))
    try:
        opener.open(urllib.request.Request(authorize_url))
    except urllib.error.HTTPError as e:
        app.infoBox("Can't get osm id", "Please retry and report this issue with the error code on https://github.com/openstreetcam/uploader. Error: {}".format(e))
    
    pin = cj._cookies['www.openstreetmap.org']['/']['_osm_session'].value

    try:
        request_token_access, request_token_secret_access = \
            osm.get_access_token(request_token,
                                 request_token_secret,
                                 method='POST',
                                 data={'oauth_verifier': pin})
        data_access = {'request_token': request_token_access,
                       'secret_token': request_token_secret_access
                       }
        resp_access = requests.post(url=url_access, data=data_access)
        access_token = resp_access.json()['osv']['access_token']
        token_file = open("access_token.txt", "w+")
        token_file.write(access_token)
        token_file.close()
    except Exception as ex:
        print(ex)
        print("ERROR LOGIN no GRANT ACCES")
        sys.exit()
    app.setMessage("okOAuthStep2", "OK")
    app.setButtonState("Get Access Token", "disabled")


def scanSourceFolder():
    global upload_dir
    path = upload_dir

    local_dirs = os.listdir()
    if str(path).replace('/', '') in local_dirs:
        path = os.getcwd() + '/' + path
    if os.path.basename(path) != "":
        path += "/"

    old_dir = os.getcwd()
    os.chdir(path)
    photos_path = sorted(os.listdir(path), key=os.path.getmtime)
    os.chdir(old_dir)
    time_stamp_list = []
    exist_timestamp = True
    photos_found = False
    for photo_path in [p for p in photos_path]:
        if ('jpg' in photo_path.lower() or 'jpeg' in photo_path.lower()) and "thumb" not in photo_path.lower():
            photos_found = True
            try:
                time_stamp_list.append({"file": photo_path, "timestamp": get_exif(path + photo_path).values})
            except:
                exist_timestamp = False
                photos_path = sorted(os.listdir(path), key=itemgetter(1, 2))
    if not photos_found:
        print ("No photos found in path \"%s\"." % (path))
        print ("This program does not search for files in subdirectories of the given path.")
        sys.exit()
    if exist_timestamp:
        time_stamp_list = sorted(time_stamp_list, key=itemgetter('timestamp'))
        photos_path = []
        for element in time_stamp_list:
            photos_path.append(element['file'])
    for photo_path in [p for p in photos_path]:
        if ('jpg' in photo_path.lower() or 'jpeg' in photo_path.lower()) and "thumb" not in photo_path.lower():
            try:
                latitude, longitude, compas = get_gps_lat_long_compass(path + photo_path)
            except Exception:
                try:
                    tags = exifread.process_file(open(path + photo_path, 'rb'))
                    latitude, longitude = get_exif_location(tags)
                    if latitude is None and longitude is None:
                        latitude, longitude, compas = get_data_from_json(path, photo_path)
                except Exception as ex:
                    print (ex)
                    continue
            data_sequence = {'uploadSource': 'Python',
                             'access_token': access_token,
                             'currentCoordinate': str(latitude) + ',' + str(longitude)
                             }
            if latitude is not None and longitude is not None:
                break
    try:
        with open(path + "sequence_file.txt", "r+") as sequence_file:
            id_sequence = sequence_file.read()
            sequence_file.close()
    except Exception as ex:
        with open(path + "sequence_file.txt", "w+") as sequence_file:
            if latitude is None and longitude is None:
                print("Error. There is no latitude and longitude in images.")
                sys.exit()
            h = requests.post(url_sequence, data=data_sequence)
            try:
                id_sequence = h.json()['osv']['sequence']['id']
            except Exception as ex:
                print("Fail code:" + str(ex))
                print("Fail to create the sequence")
                os.remove(path + "sequence_file.txt")
                print("Please restart the script")
                sys.exit()
            sequence_file.write(id_sequence)
            sequence_file.close()
    try:
        photos_path.remove("sequence_file.txt")
    except Exception as ex:
        print("No sequence file existing")
    count_list = []
    try:
        count_file = open(path + "count_file.txt", "r")
        lines = count_file.readlines()
        for line in lines:
            count_list.append(int(line.replace('\n', '').replace('\r', '')))
            count = int(line.replace('\n', '').replace('\r', ''))
    except:
        count = 0
    nr_photos_upload = 0
    for photo_path in [p for p in photos_path]:
        if ('jpg' in photo_path.lower() or 'jpeg' in photo_path.lower()) and "thumb" not in photo_path.lower():
            nr_photos_upload += 1
    print("Found " + str(nr_photos_upload) + " pictures to upload")
    local_count = 0
    list_to_upload = []
    int_start = 0
    count_uploaded = count
    global COUNT_TO_WRITE
    COUNT_TO_WRITE = count
    global START_TIME
    START_TIME = time.time()


def get_exif(path):
    with open(path, 'rb') as fh:
        tags = exifread.process_file(fh, stop_tag="EXIF DateTimeOriginal")
        dateTaken = tags["EXIF DateTimeOriginal"]
        return dateTaken


# Build the UI
app = gui(TITLE)

app.addLabel("title", TITLE)
app.addMessage("instructions", INSTRUCTIONS)

app.startLabelFrame("0. Grant Access")
if not hasToken():
    app.addMessage("oauthMessageStep1", """This application needs read access to your basic OSM account information. 
This is done through a mechanism called OAuth. This way we don't need your OSM username and password. 
There are two steps. The first step is retrieving access tokens. This involves opening a browser window that lets you log in to OSM and grant access to your basic account information.""")
    app.addButton("Get Request Token", getRequestTokens)
    app.addMessage("okOAuthStep1", "")
    app.setMessageFg("okOAuthStep1", "#339933")
    app.addMessage("oauthMessageStep2", """The second step involves getting an access token using the request tokens we received in step 1. This token is stored in a file 'access_token.txt'. Don't share this file!""")
    app.addButton("Get Access Token", GetAccessToken)
    app.addMessage("okOAuthStep2", "")
    app.setMessageFg("okOAuthStep2", "#339933")
else:
    app.addMessage("oauthMessage", "OK")
    app.setMessageFg("oauthMessage", "#339933")
app.stopLabelFrame()

app.startLabelFrame("1. Select Upload Type")
app.addRadioButton("uploadtype", uploadTypes["exif"])
# app.addRadioButton("uploadtype", uploadTypes["app"])  # (not supported for now)
app.addMessage("unsuported", """Only EXIF uploads supported for now.
Please use the Python script to upload photos from mobile app directory""")
app.stopLabelFrame()


app.startLabelFrame("2. Select Directory")
app.addButton("Select Directory", pickDirectory)
app.stopLabelFrame()

app.addMessage("dirname", upload_dir)

app.startLabelFrame("3. Upload")
app.addButton("Upload", doUpload)
app.stopLabelFrame()



app.go()
