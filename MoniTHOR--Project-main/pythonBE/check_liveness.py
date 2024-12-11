from datetime import datetime
import requests
import json
import concurrent.futures
from queue import Queue
import time
from pythonBE import check_certificate 
import os
from pythonBE.logs import logger

# livness and ssl info function , for single domain file "all=False" , for domains file "all=True"
# function will read Domain/Domains file and will update relevant fields in file 
# 'domain','status_code',"ssl_expiration","ssl_Issuer" 

def livness_check (username):
    # Measure start time
    now = datetime.now() # Format the date and time in a friendly way 
    start_date_time = now.strftime("%H:%M  %d/%m/%y ")
    start_time = time.time()    
    urls_queue = Queue()
    analyzed_urls_queue = Queue()
    
    fileToCheck=f'./userdata/{username}_domains.json'
    
    if not os.path.exists(fileToCheck):
        return "Domains file is not exist"
        
    with open(fileToCheck, 'r') as f:
        currentListOfDomains=list(json.load(f))       
     
    for d in currentListOfDomains :        
        urls_queue.put(d['domain']) 
         
    numberOfDomains=urls_queue.qsize()
    logger.info(f"Total URLs to check: {numberOfDomains} for user {username}")

    # Define the URL checking function with a timeout and result storage
    def check_url():
        while not urls_queue.empty():
            url = urls_queue.get()
            
            
            
            #print(certInfo)
            result = {'domain': url, 'status_code': 'FAILED' ,"ssl_expiration":'FAILED',"ssl_Issuer": 'FAILED' }  # Default to FAILED
            try:
                response = requests.get(f'http://{url}', timeout=10)
                
                if response.status_code == 200:                    
                    certInfo=check_certificate.certificate_check(url) 
                    result = {'domain': url, 'status_code': 'OK' ,"ssl_expiration":certInfo[0],"ssl_Issuer": certInfo[1][:30]}  # Default to FAILED
            except requests.exceptions.RequestException:
                result['status_code'] = 'FAILED'
            finally:
                analyzed_urls_queue.put(result)  # Add result to analyzed queue
                urls_queue.task_done()

    # Generate report after all URLs are analyzed
    def generate_report():
        results = []
        urls_queue.join()  # Wait for all URL checks to finish

        # Collect results from analyzed queue
        while not analyzed_urls_queue.empty():
            results.append(analyzed_urls_queue.get())
            analyzed_urls_queue.task_done()

        # Write results to JSON file
        with open(fileToCheck, 'w') as outfile:
            json.dump(results, outfile, indent=4)
        

    # Run URL checks in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=100) as liveness_threads_pool:
        # Submit URL check tasks
        futures = [liveness_threads_pool.submit(check_url) for _ in range(100)]
        # Generate report after tasks complete
        liveness_threads_pool.submit(generate_report)

    urls_queue.join()  # Ensure all URLs are processed

    # Measure end time
    end_time = time.time()
    elapsed_time = end_time - start_time
    
    logger.info(f"URL liveness check complete in {elapsed_time:.2f} seconds.")
    with open(f'./userdata/{username}_domains.json', 'r') as f:
        results = json.load(f)
    return start_date_time,str(numberOfDomains)

