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
import threading
import time
from concurrent import futures

TITLE = "OpenStreetCam Upload"
INSTRUCTIONS = """With this application, you can upload a directory of photos to OpenStreetCam.
This can be a directory copied from the OSC app on your phone, or a directory of photos with EXIF location data from for example an action camera."""
max_workers = 4  # upload threads

path = None
authorize_url = None
osm = None
request_token = None
request_token_secret = None
access_token = None
COUNT_TO_WRITE = None
START_TIME = None
photos_path = None
count_list = None
nr_photos_upload = None
id_sequence = None
count = 0

# test endpoints
# url_sequence = 'http://testing.openstreetview.com/1.0/sequence/'
# url_photo = 'http://testing.openstreetview.com/1.0/photo/'
# url_finish = 'http://testing.openstreetview.com/1.0/sequence/finished-uploading/'
# url_access = 'http://testing.openstreetview.com/auth/openstreetmap/client_auth'

# staging endpoints
url_sequence = 'http://staging.openstreetview.com/1.0/sequence/'
url_photo = 'http://staging.openstreetview.com/1.0/photo/'
url_finish = 'http://staging.openstreetview.com/1.0/sequence/finished-uploading/'
url_access = 'http://staging.openstreetview.com/auth/openstreetmap/client_auth'


# url_sequence = 'http://openstreetcam.com/1.0/sequence/'
# url_photo = 'http://openstreetcam.com/1.0/photo/'
# url_finish = 'http://openstreetcam.com/1.0/sequence/finished-uploading/'
# url_access = 'http://openstreetcam.com/auth/openstreetmap/client_auth'

uploadTypes = {
    "app": "Directory copied from OSC app",
    "exif": "Directory of photos with EXIF location"
}


def pickDirectory(val):
    global path
    path = app.directoryBox("Directory", os.path.expanduser("~"))
    threading.Thread(target=scanSourceFolder).start()
    app.setMessage("dirname", "scanning {}...".format(path))


def doUpload(val):
    if not path:
        app.infoBox("No Directory Selected", "You didn't select a directory to upload yet")
    upload()

def hasToken():
    return os.path.isfile('access_token.txt')


def load_access_token():
    global access_token
    token_file = open("access_token.txt", "r+")
    string = token_file.read()
    access_token = string


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
    global access_token
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
    global path
    global photos_path
    global count_list
    global nr_photos_upload
    global id_sequence
    global count

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
    latitude = None
    longitude = None
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
                except Exception as ex:
                    app.setMessage("dirname", ex)
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
                app.setMessage("dirname", """Failed to create the sequence, code: {}. Please try again.""".format(str(ex)))
                os.remove(path + "sequence_file.txt")
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

    # after finishing, update UI.
    app.setMessage(
        "dirname", "{} photos found to upload.".format(
            nr_photos_upload))


def upload_photos(url_photo, dict, timeout, path):
    photo = dict['photo']
    data_photo = dict['data']
    name = dict['name']
    conn = requests.post(url_photo, data=data_photo, files=photo, timeout=timeout)
    if int(conn.status_code) != 200:
        print("Request/Response fail")
        retry_count = 0
        while int(conn.status_code) != 200:
            print("Retry attempt : " + str(retry_count))
            conn = requests.post(url_photo, data=data_photo, files=photo, timeout=timeout)
            retry_count += 1
    photo['photo'][1].close()
    with open(path + "count_file.txt", "a+") as fis:
        global COUNT_TO_WRITE
        COUNT_TO_WRITE += 1
        fis.write((str(COUNT_TO_WRITE)) + '\n')
        fis.close()
    return {'json': conn.json(), 'name': name}


def thread(max_workers, url_photo, list_to_upload, path, count_uploaded, total_img):
    with futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(upload_photos, url_photo, dict, 1000, path): dict for dict in list_to_upload}
        for future in futures.as_completed(future_to_url):
            try:
                data = future.result()['json']
                name = future.result()['name']
                
                if max_workers >=  float(COUNT_TO_WRITE):
                        estimated_time = '...'
                else:
                        elapsed_time = time.time() - START_TIME
                        estimated_time = str(timedelta(seconds=(elapsed_time/(COUNT_TO_WRITE))*(total_img-COUNT_TO_WRITE))).split(".")[0]
                        
   
                print("processing {}".format(name))
                if data['status']['apiCode'] == "600":
                    percentage = float((float(COUNT_TO_WRITE) * 100) / float(total_img))
                    print(("Uploaded - " + str(COUNT_TO_WRITE) + ' of total :' + str(
                        total_img) + ", percentage: " + str(round(percentage, 2)) + "%"+" ET:"+estimated_time))
                elif data['status']['apiCode'] == "610":
                    print("skipping - a requirement arguments is missing for upload")
                elif data['status']['apiCode'] == "611":
                    print("skipping - image does not have GPS location metadata")
                elif data['status']['apiCode'] == "660":
                    print("skipping - duplicate image")
                else:
                    print (data['status'])
                    print("skipping - bad image")
            except Exception as exc:
                print (exc)
                print ("Uploaded error")
    return count_uploaded


def upload():
    global count
    local_count = 0
    list_to_upload = []
    int_start = 0
    count_uploaded = 0
    global COUNT_TO_WRITE
    COUNT_TO_WRITE = 0
    global START_TIME
    START_TIME = time.time()

    for index in range(int_start, len([p for p in photos_path])):
        photo_to_upload = photos_path[index]
        local_count += 1
        if ('jpg' in photo_to_upload.lower() or 'jpeg' in photo_to_upload.lower()) and \
                        "thumb" not in photo_to_upload.lower() and local_count not in count_list:
            total_img = nr_photos_upload
            photo_name = os.path.basename(photo_to_upload)
            try:
                photo = {'photo': (photo_name, open(path + photo_to_upload, 'rb'), 'image/jpeg')}
                try:
                    latitude, longitude, compas = get_gps_lat_long_compass(path + photo_to_upload)
                except Exception:
                    try:
                        tags = exifread.process_file(open(path + photo_to_upload, 'rb'))
                        latitude, longitude = get_exif_location(tags)
                        compas = -1
                        # if latitude is None and longitude is None:
                        #     latitude, longitude, compas = get_data_from_json(path, photo_path)
                    except Exception:
                        continue
                if compas == -1:
                    # TODO: add 'acces_token': acces_token,
                    data_photo = {'access_token': access_token,
                                  'coordinate': str(latitude) + "," + str(longitude),
                                  'sequenceId': id_sequence,
                                  'sequenceIndex': count
                                  }
                else:
                    data_photo = {'access_token': access_token,
                                  'coordinate': str(latitude) + "," + str(longitude),
                                  'sequenceId': id_sequence,
                                  'sequenceIndex': count,
                                  'headers': compas
                                  }
                info_to_upload = {'data': data_photo, 'photo': photo, 'name': photo_to_upload}
                list_to_upload.append(info_to_upload)
                if count != local_count:
                    count += 1
            except Exception as ex:
                print(ex)
        if (index % 100 == 0 and index != 0) and local_count not in count_list:
            count_uploaded = thread(
                max_workers,
                url_photo,
                list_to_upload,
                path,
                count_uploaded,
                total_img)
            list_to_upload = []
    if (index % 100 != 0) or index == 0:
        count_uploaded = thread(max_workers, url_photo, list_to_upload, path, count_uploaded, nr_photos_upload)

    data_finish = {'access_token': access_token,
                   'sequenceId': id_sequence
                   }
    f = requests.post(url_finish, data=data_finish)
    if f.json()['status']['apiCode'] == '600':
        print(("Finish uploading from dir: " + path + " with sequence id: " + str(id_sequence)))
    else:
        print(("FAIL uploading from dir: " + path))
        print("Error: ")
        print(f.json())


def _get_if_exist(data, key):
    if key in data:
        return data[key]

    return None


def _convert_to_degress(value):
    d = float(value.values[0].num) / float(value.values[0].den)
    m = float(value.values[1].num) / float(value.values[1].den)
    s = float(value.values[2].num) / float(value.values[2].den)

    return d + (m / 60.0) + (s / 3600.0)


def get_exif(path):
    with open(path, 'rb') as fh:
        tags = exifread.process_file(fh, stop_tag="EXIF DateTimeOriginal")
        dateTaken = tags["EXIF DateTimeOriginal"]
        return dateTaken


def get_exif_location(exif_data):
    lat = None
    lon = None

    gps_latitude = _get_if_exist(exif_data, 'GPS GPSLatitude')
    gps_latitude_ref = _get_if_exist(exif_data, 'GPS GPSLatitudeRef')
    gps_longitude = _get_if_exist(exif_data, 'GPS GPSLongitude')
    gps_longitude_ref = _get_if_exist(exif_data, 'GPS GPSLongitudeRef')

    if gps_latitude and gps_latitude_ref and gps_longitude and gps_longitude_ref:
        lat = _convert_to_degress(gps_latitude)
        if gps_latitude_ref.values[0] != 'N':
            lat = 0 - lat

        lon = _convert_to_degress(gps_longitude)
        if gps_longitude_ref.values[0] != 'E':
            lon = 0 - lon

    return lat, lon


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
    load_access_token()
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

app.addMessage("dirname", path)

app.startLabelFrame("3. Upload")
app.addButton("Upload", doUpload)
app.stopLabelFrame()



app.go()
