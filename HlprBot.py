# Based on the code from /u/INeverQuiteWas
# Adapted by /u/_ihavemanynames_
# Help from  http://praw.readthedocs.io/en/latest/tutorials/comments.html
# EXCLUDES TOP LEVEL COMMENTS

import praw
import sys
from collections import Counter

def check_top_level(cmt, id):   
    parent = cmt.parent()
    comparent = parent.id
    if comparent == id:
        return True
    else:
        return False
    
 
class Bot:
 
    def __init__(self, reddit):
        self.reddit = reddit
 
    @property
    def submissions(self):
        try:
            return [self.reddit.submission(id=arg) for arg in sys.argv[1:]]
        except Exception as e:
            print(e)
            return [str(e)]
 
    @property
    def data(self):
        names = []
        for post in self.submissions:
            post.comments.replace_more(limit=0)

            for comment in post.comments.list():
                
                top_level = check_top_level(comment, post.id)
                if top_level is True:
                    continue
                
                try:
                    user = str(comment.author.name)
                except AttributeError:
                    print("User has deleted their account")
                    continue 
                try:
                   names.append(user)
                except:
                    pass
        
        return Counter(names)
 
def main():
    reddit = praw.Reddit(
	'NameHere', 
	user_agent='AgentNameHere')
    print("Authenticated as u/" + reddit.user.me().name)
    x = Bot(reddit).data
    message = ""
    for thing in x:
        message += "{}: {}\n".format(thing, x[thing])
    with open('data.txt', 'w') as f:
        f.write(message)
 
 
if __name__ == '__main__':
    main()