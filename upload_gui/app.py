import os
from appJar import gui
from rauth import OAuth1Service
from http import cookiejar
import urllib
import sys
import requests
import webbrowser
import platform

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


app = gui(TITLE)

app.addLabel("title", TITLE)

app.addMessage("instructions", INSTRUCTIONS)

app.startLabelFrame("0. Grant Access")
if not hasToken():
    app.addMessage("oauthMessageStep1", """This application needs read access to your basic OSM account information. 
This is done through a mechanism called OAuth. This way we don't need your OSM username and password. 
There are two steps. The first step is retrieving access tokens. This involves opening a browser window that lets you log in to OSM and grant access to your basic account information.""")
    app.addButton("Get Request Token", getRequestTokens)
    app.addMessage("oauthMessageStep2", """The second step involves getting an access token using the request tokens we received in step 1. This token is stored in a file 'access_token.txt'. Don't share this file!""")
    app.addButton("Get Access Tokens", GetAccessToken)
else:
    app.addMessage("oauthMessage", """We have a token, good to go""")
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
