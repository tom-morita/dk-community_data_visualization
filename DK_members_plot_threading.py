import requests
import sys
import urllib.parse
from bs4 import BeautifulSoup
import warnings;warnings.filterwarnings('ignore') # ssl証明書エラーを抑制
import copy
import ast


from concurrent.futures import ThreadPoolExecutor
import queue
from requests_toolbelt.threaded import pool

import numpy as np
import datetime
#import time
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.dates import DateFormatter
from matplotlib.dates import date2num
from matplotlib import ticker
from collections import Counter



manage_url = "https://manage.doorkeeper.jp"
event_list = []
user_list = []

proxies ={"https":"http://127.0.0.1:8080","http":"http://127.0.0.1:8080",}



def dk_login():
    cookies = {}
    print("[>] You should login for web scraping.")
    my_id = input("[?] Input your ID :")
    my_pass = input("[?] Input your PASS :")

    # Req:1 GET /user/sign_in
    url = manage_url + "/user/sign_in"
    headers = {}
    r = requests.get(url, headers=headers, cookies=cookies, allow_redirects=False) #, proxies=proxies, verify=False)
    cookies.update(r.cookies)
    bs = BeautifulSoup(r.text, 'html.parser')
    authenticity_token = bs.find(attrs={'name':'authenticity_token'}).get('value')


    # Req:2 POST /user/sign_in
    url = manage_url + "/user/sign_in"
    login_data = {
        'user[email]': my_id,
        'user[password]': my_pass,
        # 'utf8': '✓',
        # 'user[remember_me]': "0",
        # 'commit': 'アカウントにログイン'
        }
    login_data['authenticity_token'] = urllib.parse.quote(authenticity_token, encoding="utf8", safe="+%=/\\")
    payload = login_data
    r = requests.post(url, data=payload, headers=headers, cookies=cookies, allow_redirects=False, proxies=proxies, verify=False)
    auth_error="Invalid email or password."
    if auth_error in r.text:
        print("[!]", auth_error)
        sys.exit(-1)
        
    cookies.update(r.cookies)


    # Req:3 GET /
    url = manage_url + "/"
    r = requests.get(url, headers=headers, cookies=cookies, allow_redirects=False) #, proxies=proxies, verify=False)
    cookies.update(r.cookies)


    # Req:4 GET /user/events
    url = manage_url + "/user/events"
    r = requests.get(url, headers=headers, cookies=cookies, allow_redirects=False) #, proxies=proxies, verify=False)
    cookies.update(r.cookies)


    # Req:5 GET /user/groups
    url = manage_url + "/user/groups"
    r = requests.get(url, headers=headers, cookies=cookies, allow_redirects=False) #, proxies=proxies, verify=False)
    cookies.update(r.cookies)

    # Scraping
    stream = r.text.split("<div class='panel' id='adminCommunities'>")[-1] # あなたが主催者
    stream = stream.split("</div>\n<div class='panel' id='memberCommunities'>")[0] # あなたがメンバー

    soup = BeautifulSoup(stream, "html.parser")
    a_all = soup.find_all("a", attrs={"class":"list-group-item"})
    #print(soup.a.string)

    adminCommunities = []
    for a_soup in a_all:
        adminCommunities.append(a_soup.get('href'))

    if len(adminCommunities) > 1:
        for i,j in enumerate(adminCommunities):
            print("\t", i, j.split("/")[-1], j)
        i = int(input("[?] Choice Your Community(0-" + str(len(adminCommunities)) + ") :"))
        group_url = adminCommunities[i]
    else:
        print("[+] Your Community :")
        group_url = adminCommunities[0]

    print("\t", group_url)
    return cookies, group_url

    
def get_event_list(cookies, group_url):
    event_url = group_url + "/events"
    event_branch = event_url.split(manage_url)[-1]
    print("[+] Event page :", event_branch)
    headers = {}
    
    # すべてのイベントのURL、イベント名、参加者数、参加者上限、開催日をリスト化
    # {"url":"","name":"","attendance":"","capacity":"","date":"",}
    event_list = []
    page_num = 1
    event_num = 0
    count_num = 0
    date_num = 0
    
    while True:
        event_info = {}
        r = requests.get(event_url+"?page="+str(page_num), headers=headers, cookies=cookies) #,proxies=proxies, verify=False)
        soup = BeautifulSoup(r.text, "html.parser")
        if "<span>イベントはありません。</span>" in r.text:
            break

        a_all = soup.find_all("a")

        for a_soup in a_all:
            val = a_soup.get('href')
            if str(val).startswith(event_branch):
                if not val == event_branch:
                    if not "?" in str(val):
                        if not "new" in str(val):
                            event_info["num"] = event_num
                            event_info["url"] = val
                            event_info["id"] = val.split("/")[-1]
                            event_info["title"] = a_soup.getText()
                            event_list.append(copy.deepcopy(event_info))
                            event_num += 1
    

        # <td class='nobreak' style='width: 20px'><span>162 / 176 people</span></td>
        # <div class='event-item-count'><span>123 / 143人</span></div>
        count_all = soup.find_all("div", class_="event-item-count")
        for count_soup in count_all:
            val = count_soup.getText()
            if "people" in val or "人" in val:
                val = val.replace("people","")
                val = val.replace("人","")
                # 162 / 176 people            
                val = val.split("/")
                event_list[count_num]["attendance"] = int(val[0].strip())
                event_list[count_num]["capacity"] = int(val[1].strip())
                count_num += 1

        date_all = soup.find_all("div", class_="event-item-date nobreak")
        for date_soup in date_all:
            val = date_soup.getText()
            event_list[date_num]["date"]=val.split(" ")[0]
            date_num += 1

        page_num += 1


    def req_events(event):
        r = requests.get(manage_url+event["url"], headers=headers, cookies=cookies) #,proxies=proxies, verify=False)
        soup = BeautifulSoup(r.text, "html.parser")
        li_all=soup.find_all("li",class_="list-group-item activity-item")
        for li in li_all:
            if "公開されました" in str(li):
                event["publish"] = li.find("div",class_="activity-item-date").getText()
        print("*",end="")
        return event["num"]

    with ThreadPoolExecutor(max_workers=100) as executor:
        results = list(executor.map(req_events, event_list))

    print("\n",results)

    print("[+]", len(event_list), "events are found.")
    for i,info in enumerate(event_list):
        print("\t", i, info["title"])
    
    if len(event_list) == 0:
        print("[!] NO get_event : error !!!")
        sys.exit(-1)

    with open("event_list.txt", mode="w", encoding="utf-8") as f:
        for event in event_list:
            f.write(str(event) + "\n")

    return event_list


def get_member_list(cookies, group_url):
    member_url = group_url + "/members"
    headers = {}
    
    # すべてのイベントの[URL、イベント名、参加者数、参加者上限、開催日]をリスト化
    # "url", "name", "attendance", "capacity", "date"
    member_list = []
    page_num = 1
    member_num = 0
    
    while True:
        member_info = {}
        r = requests.get(member_url+"?page="+str(page_num), headers=headers, cookies=cookies) #,proxies=proxies, verify=False)
        soup = BeautifulSoup(r.text, "html.parser")
        if not "<div class='user-name'>" in r.text:
            break

        member_table = soup.find("table",{"class":"table user-profile-table-mini"})
        rows = member_table.find_all("tr")

        for row in rows:
            member = row.find_all("td")
            if len(member) >0:
                member_info["num"] = member_num
                member_info["name"] = member[0].find("a").getText()
                member_info["url"] = member[0].find("a").get("href")
                member_info["date"] = member[1].getText().split(" ")[0]
                
                member_list.append(copy.deepcopy(member_info))
                member_num += 1
        
        page_num += 1


    print("[+] Now, scraping ", len(member_list),"members pages.")


    def req_members(member):
        url = manage_url + member["url"]
        r = requests.get(url, headers=headers, cookies=cookies) #,proxies=proxies, verify=False)

        attend_list = ["x" for i in range(len(event_list))]
        soup = BeautifulSoup(r.text, "html.parser")
        events = soup.find_all("li", class_="list-group-item")
        for event in events:
            for j in range(len(event_list)):
                if event_list[j]["url"] in event.find("a").get("href"):
                    #<div class='event-item-right'><span class="label label-default">キャンセル</span></div>
                    #<div class='event-item-right'><span class="label label-success">出席済み</span></div>
                    attend_list[j] = event.find("span").getText()
            
        member["attend"] = attend_list
        member["attend_count"] = attend_list.count("出席済み")

        print("*",end="")
        return member["num"]


    with ThreadPoolExecutor(max_workers=100) as executor:
        results = list(executor.map(req_members, member_list))

    print("\n",results)


    print("\n\n[+] ",len(member_list)," users are found !!!")
    
    if len(member_list) == 0:
        print("[!] NO user : error !!!")
        sys.exit(-1)


    with open("member_list.txt", mode="w", encoding="utf-8") as f:
        for member in member_list:
            f.write(str(member) + "\n")

    return member_list


def check_atend_ranking(member_list):
    print("[+] TOP10 from",len(member_list),"members.")
    score={}
    for member in member_list:
        score[member["name"]] = member["attend_count"]

    score_sorted = sorted(score.items(), key=lambda x:x[1])

    ranking = []

    for i in range(1,11):
        rank = str(i) + "位:" + str(score_sorted[-1*(i)])
        print("\t", rank)
        ranking.append(rank)

    with open("attend_ranking.txt", mode="w", encoding="utf-8") as f:
        for rank in ranking:
            f.write(str(rank) + "\n")

    

def plot_member_transition(event_list, member_list):
    accept_periods = []
    for event in event_list:
        accept_periods.append([event["publish"],event["date"]])

    with open("accept_periods.txt", mode="w", encoding="utf-8") as f:
        for period in accept_periods:
            f.write(str(period)+"\n")
        
    # accept_periods=[['start_YMD','end_YMD'],,,]
    # Join_per_day  = ['join_YMD',,,]
    Join_per_day = [member["date"] for member in member_list]
    Join_per_week = []

       
    def text(x, y, text):
        ax1.text(x, y, text, ha='center', va='top', color='tab:red', alpha=0.5)

    def ret_strptime(str_date):
       return datetime.datetime.strptime(str_date, "%Y-%m-%d")


    # data for plot
    min_day = min(min([day[0] for day in accept_periods]), min(Join_per_day))
    max_day = max(max([day[1] for day in accept_periods]), max(Join_per_day))
    dt_min = ret_strptime(min_day)
    dt_min = dt_min.replace(day=1)
    dt_max = ret_strptime(max_day)
    dt_max = dt_max.replace(month=dt_max.month+1, day=1)


    # week-data for plot / merge isocalender-week
    for date in Join_per_day:
       dt_temp = ret_strptime(date)
       dt_temp = dt_temp - datetime.timedelta(dt_temp.isocalendar()[-1])
       Join_per_week.append(dt_temp)

    join_week, value_week = zip(*(sorted(Counter(Join_per_week).items())))
    x1 = [date for date in join_week]
    y1 = value_week


    # total-members for plot / Cumulative sum
    join_day, value_day = zip(*(sorted(Counter(Join_per_day).items())))
    x2 = [date2num(ret_strptime(date)) for date in join_day]
    y2 = np.cumsum(value_day)


    group_name = event_list[0]["url"].split("/")[2]
    fig, ax1 = plt.subplots()
    yax1 = ax1.yaxis
    yax1.grid(True)
    ax1.set_title(group_name, fontsize=10)
    ax2 = ax1.twinx()


    # change datetime to float
    for period in accept_periods:
       period[0] = ret_strptime(period[0])
       period[1] = ret_strptime(period[1])

    i=0
    for period in accept_periods:
        ax1.axvspan(period[0], period[1], facecolor='tab:green', alpha=0.15)
        ax1.axvline(x=(period[1]),linewidth=1, color='tab:red', alpha=0.5)
        text(period[1], max(y1)*(0.9-0.5*i/len(accept_periods)) , str(len(accept_periods)-i))
        i += 1


    # x-axis format
    xax2 = ax2.xaxis
    months = mdates.MonthLocator()
    new_xticks = date2num(
            [datetime.datetime(x,y,1)
            for x in range(dt_min.year, dt_max.year+1)
            for y in range(1,12+1)[3::6]]
            ) 
    xax2.set_major_formatter(DateFormatter('%Y-%m'))
    xax2.set_major_locator(ticker.FixedLocator(new_xticks))
    xax2.set_minor_locator(months)
    fig.autofmt_xdate(rotation=60)


    # plot
    ax1.set_ylabel("New members per week")
    ax2.set_ylabel("Total members")
    line1 = ax1.bar(x1, height=y1, width=6, color='tab:blue', label="per_week")
    line2 = ax2.plot(x2, y2, color='tab:orange', label="total")

    # legend
    lines = [line1] + line2
    labels = [line.get_label() for line in lines]
    ax2.legend(lines, labels, loc="best")

    plt.show()
    


if __name__ == '__main__':
    print(datetime.datetime.now())

    while True:
        flag = input("[?] WebScraping[Y] or LocalLogfile[N] :")
        if flag in "YyＹｙ":
            i,j = dk_login()
            event_list = get_event_list(i,j)
            member_list = get_member_list(i,j)
            break
            
        elif flag in "NnＮｎ":
            event_list = []
            member_list = []

            with open("event_list.txt", mode="r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in lines:
                    event_list.append(ast.literal_eval(line))
                    
            with open("member_list.txt", mode="r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in lines:
                    member_list.append(ast.literal_eval(line))

            break

    check_atend_ranking(member_list)
    plot_member_transition(event_list, member_list)
    print(datetime.datetime.now())
    input("[!] end,,, (press any key)")


