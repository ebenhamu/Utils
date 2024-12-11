from logging import Logger
from flask import Flask, session, render_template,render_template_string,redirect,request, url_for
import requests
from oauthlib.oauth2 import WebApplicationClient
from pythonBE import user , check_liveness ,domain
from pythonBE.logs import logger
import json
from dotenv import load_dotenv
import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
import pytz
import uuid
from datetime import datetime 
import threading 
import time
import os
import glob

# Load environment variables from .env file
load_dotenv()

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)  # __name__ helps Flask locate resources and configurations
app.secret_key = os.getenv('FLASK_SECRET_KEY')

# Global parmeters to keep last job info.
global globalInfo 
globalInfo = {'runInfo': ('--:--  --/--/-- ', '-')}

# Google OAuth2 details
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
GOOGLE_DISCOVERY_URL = os.getenv('GOOGLE_DISCOVERY_URL')

# Initialize OAuth2 client
client = WebApplicationClient(GOOGLE_CLIENT_ID)

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.start()

scheduled_jobs = [] # Store scheduled jobs




@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return 'No file part'
    file = request.files['file']
    if file.filename == '':
        return 'No selected file'
    if file:
        file.save('./upload/' + file.filename)
        return 'File successfully uploaded'

# Route for Job schedule 
@app.route('/schedule_bulk_monitoring', methods=['POST'])
def schedule_bulk_monitoring():
    # Get form data    
    schedule_time = request.form['schedule_time']
    timezone = request.form['timezone']
    interval = request.form.get('interval')
    user = session['user']    

    # Convert time to UTC
    local_tz = pytz.timezone(timezone)
    local_time = local_tz.localize(datetime.fromisoformat(schedule_time))
    utc_time = local_time.astimezone(pytz.utc)

    # Generate a unique job ID
    job_id = str(uuid.uuid4())

    if interval:
        # Schedule a recurring job
        scheduler.add_job(Checkjob,trigger='interval',hours=int(interval),args=[user],id=job_id,start_date=utc_time)
    else:
        # Schedule a one-time job
        scheduler.add_job(Checkjob,trigger=DateTrigger(run_date=utc_time),args=[user],id=job_id)
    
    # Save job info
    scheduled_jobs.append({'id': job_id,'user': user,'time': schedule_time,'timezone': timezone,'interval': interval})    

    return {'message': 'Monitoring scheduled successfully!'}

# Route for job cancel 
@app.route('/cancel_job/<job_id>', methods=['POST'])
def cancel_job(job_id):
    scheduler.remove_job(job_id)
    global scheduled_jobs
    scheduled_jobs = [job for job in scheduled_jobs if job['id'] != job_id]
    return {'message': 'Job canceled successfully!'}

#Route for Google Authentication
@app.route('/google-login')
def google_login():
    google_provider_cfg = requests.get(GOOGLE_DISCOVERY_URL).json()
    authorization_endpoint = google_provider_cfg['authorization_endpoint']

    # Generate the authorization URL
    request_uri = client.prepare_request_uri(
        authorization_endpoint,
        redirect_uri=url_for('google_callback', _external=True),
        scope=["openid", "email", "profile"],
    )
    return redirect(request_uri)

# Route For Google Callback
@app.route('/callback')
def google_callback():
    # Get the authorization code Google sent back
    code = request.args.get("code")

    google_provider_cfg = requests.get(GOOGLE_DISCOVERY_URL).json()
    token_endpoint = google_provider_cfg["token_endpoint"]

    # Prepare token request
    token_url, headers, body = client.prepare_token_request(
        token_endpoint,
        authorization_response=request.url,
        redirect_url=url_for('google_callback', _external=True),
        code=code
    )
    token_response = requests.post(
        token_url,
        headers=headers,
        data=body,
        auth=(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET),
    )

    # Parse tokens
    client.parse_request_body_response(json.dumps(token_response.json()))

    # Get user info
    userinfo_endpoint = google_provider_cfg["userinfo_endpoint"]
    uri, headers, body = client.add_token(userinfo_endpoint)
    userinfo_response = requests.get(uri, headers=headers, data=body)

    # Extract user info
    userinfo = userinfo_response.json()
    if userinfo.get("email_verified"):
        google_user = {
            "username": userinfo["email"]
        }
        logger.info(f'{userinfo["email"]} Login With Google Account')
        # Save the user to users.json if not already saved
        with open('users.json', 'r') as f:
          current_info = json.load(f)
          currentListOfUsers=list(current_info)

        # Check if the user already exists
        if not any(user['username'] == google_user["username"] for user in currentListOfUsers):
            currentListOfUsers.append({"username": google_user["username"]})
            with open('users.json', 'w') as f:
                json.dump(currentListOfUsers, f, indent=4)

        # Log the user in and redirect to the dashboard
        session['user'] = google_user["username"]
        return redirect(url_for("main"))
    else:
        return "User email not available or not verified by Google."
    

# Route for login page 
@app.route('/', methods=['GET'])
def home():
        return render_template('login.html')

# Route for login page 
@app.route('/login', methods=['GET', 'POST'])
def login():
    username = request.args.get('username',default=None)
    password = request.args.get('password',default=None)
    logger.debug( f"Attempt To Login With- User:{username}, Pass:{password}")    #
    status = user.login_user(username,password) 
    logger.info(f"User:{username} Login")
    if "Login Successful"== status['message']:
        session['user']=username        
        globalInfo['runInfo']=['--:--  --/--/-- ', '-']
        return "Login Successful"    
    return render_template('login.html')

# Route for Dashboard  
@app.route('/dashboard', methods=['GET'])
def main():
    user_file = f'./userdata/{session['user']}_domains.json'
    globalInfo['runInfo']=['--:--  --/--/-- ', '-']
    if os.path.exists(user_file):
     with open(user_file, 'r') as f:
          data = json.load(f)
    else:
        data = []      

    # Extract the required parts for the forms
    all_domains = [item['domain'] for item in data]  # List of domain names
    latest_results = data[:6]  # Last 6 results
    
    failuresCount = sum(1 for item in data if item.get('status_code') == 'FAILED' )    
    if len(all_domains)>0 :
        
        failuresPrecent=  round (float(float(failuresCount)/float(len(all_domains)))*100,1)
    else:
        failuresPrecent=0
    
    
    # Pass scheduled jobs for the current user
    user_jobs = [job for job in scheduled_jobs if job['user'] == session['user']]
    utc_timezones = [tz for tz in pytz.all_timezones if tz.startswith('UTC')]    
    
    
    return render_template('dashboard.html', user=session['user'], data=data, all_domains=all_domains, latest_results=latest_results, scheduled_jobs=user_jobs,
                            utc_timezones=utc_timezones,last_run=globalInfo['runInfo'][0] ,number_of_domains=f"{globalInfo['runInfo'][1]} failures {failuresPrecent} %" )

# Route for user results
@app.route('/results', methods=['GET'])
def results():
    user_file = f'./userdata/{session['user']}_domains.json'
    if os.path.exists(user_file):
     with open(user_file, 'r') as f:
          data = json.load(f)
    else:
        data = []      

    # Extract the required parts for the forms
    all_domains = [item['domain'] for item in data]  # List of domain names
    latest_results = data[:6]  # Last 6 results
    # Calculate failures 
    failuresCount = sum(1 for item in data if item.get('status_code') == 'FAILED' )
    if len(all_domains)>0 :
        failuresPrecent=  round (float(float(failuresCount)/float(len(all_domains)))*100,1)
    else:
        failuresPrecent=0   
    lastRunInfo=f"{globalInfo['runInfo'][0]} , {globalInfo['runInfo'][1]} Domains , {failuresPrecent}% failures"
    
    return render_template('results.html', user=session['user'], data=data, all_domains=all_domains, latest_results=latest_results,last_run=lastRunInfo)

# Route for Logoff
@app.route('/logoff', methods=['GET'])
def logoff():
    user=session['user']
    if user=="":
        return  ("No user is logged in")    
    session['user']=""    
    globalInfo['runInfo']=['--:--  --/--/-- ', '-']
    return  render_template('login.html')



# Route for Register 
@app.route('/register', methods=['GET', 'POST'])
def register():
    username = request.args.get('username')
    password1 = request.args.get('password1')
    password2 = request.args.get('password2')
    logger.debug(f"Received: username={username}, password1={password1}, password2={password2}")
    # Process registration
    status = user.register_user(username, password1, password2)

    # Validate input parameters
    if password1 != password2:        
        return "Passwords do not match"
    if status['message'] == 'Username already taken':
        return "Username already taken"
    if status['message'] == 'Registered successfully':
        return "Registered successfully"         

    return render_template('register.html')
    





# @app.route('/submit', methods=['POST'])
# def submit_data():
#     data = request.get_json()  # Parse JSON payload
#     return {"received": data}, 200

# Route to add a single domain 
@app.route('/add_domain/<domainName>',methods=['GET', 'POST'])
def add_new_domain(domainName):
    logger.debug(f'Route being code {domainName}')
    if session['user']=="" :
        return "No User is logged in" 
    # Get the domain name from the form data
    logger.debug(f'Domain name is {domainName}')
        
    return domain.add_domain(session['user'],domainName)   
    
# Route to remove a single domain 
@app.route('/remove_domain/<domainName>', methods=['GET', 'POST'])
def remove_domain(domainName):
    logger.debug(f'Route being called with domain: {domainName}')
    if session['user'] == "":
        return "No User is logged in"

    logger.debug(f'Domain name is {domainName}')    
    response = domain.remove_domain(session['user'], domainName)

    if response['message'] == "Domain successfully removed":       
        try:
            logger.debug(f"Before update: globalInfo['runInfo']: {globalInfo['runInfo']}")
            current_count = int(globalInfo['runInfo'][1])
            globalInfo['runInfo'] = (globalInfo['runInfo'][0], str(current_count - 1))
            logger.debug(f"After update: globalInfo['runInfo']: {globalInfo['runInfo']}")
        except ValueError:
            logger.error(f"Invalid value in globalInfo['runInfo'][1]: {globalInfo['runInfo'][1]}")
            globalInfo['runInfo'] = (globalInfo['runInfo'][0], '0')  # Fallback value

        return response
    
    
    return "Error: Domain could not be removed"
    

# usage : http://127.0.0.1:8080/bulk_upload/.%5Cuserdata%5CDomains_for_upload.txt 
# using  %5C instaed of  "\"  
# in UI put    ./userdata/Domains_for_upload.txt

@app.route('/bulk_upload/<filename>')
def add_from_file(filename):    
    if session['user']=="" :
        return "No User is logged in"         
    print(filename)  
    logger.info(f"File:{filename}")
    return domain.add_bulk(session['user'],filename)
    
    
# Route to run Livness check 
@app.route('/check/<username>')
def check_livness(username):    
    if session['user']=="" :
        return "No User is logged in" 
    globalInfo["runInfo"]=check_liveness.livness_check (username)        
    return globalInfo["runInfo"]
    
@app.route('/user')
def get_user():           
    return session['user']    

@app.route('/performance_test/<numberOfUsers>/<numberOfDomains>')
def performance_test(numberOfUsers,numberOfDomains):    
    logger.info(f"Testing {numberOfUsers} users with {numberOfDomains} domains")             

    # Specify the pattern for matching files
    pattern = './userdata/tester*.json'
    # Use glob to find files matching the pattern
    files = glob.glob(pattern)
    # Iterate over the matched files and remove them
    for file in files:
        os.remove(file)         
    
    now = datetime.now()
    start_date_time = now.strftime("%H:%M  %d/%m/%y ")
    start_time = time.time() 
    threads = []
    
    for i in range(int(numberOfUsers)): 
        thread = threading.Thread(target=runTset, args=(i,numberOfDomains)) 
        threads.append(thread) 
        thread.start()
    
    for thread in threads: 
        thread.join()
    
    logger.debug("All threads have completed.")
    end_time = time.time()
    elapsed_time = end_time - start_time
    return f"Tested {numberOfUsers} users performing concurrent for {numberOfDomains} domains checks in {elapsed_time:.2f} sec"
    
    
   




def runTset(testId,nummberOfDomains):       
    username="tester"+str(testId)+"a"
    user.register_user(username,username,username)    
    domain.add_bulk(username,"./userdata/Domains_for_upload_100.txt",nummberOfDomains)
    globalInfo["runInfo"]=check_liveness.livness_check (username)     
    
    
    return globalInfo["runInfo"]  
   
   

    


def Checkjob(username):    
    globalInfo["runInfo"]=check_liveness.livness_check (username)
    return redirect('/results')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
        
    