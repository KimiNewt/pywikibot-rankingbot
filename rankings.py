# -*- coding: utf-8 -*-
# Copyright (C) Osama Khalid 2011. Released under AGPLv3+.
# Please wirte your feedback to [[User_talk:OsamaK]].

# This script updates Alexa rankings depending on a list on
# [[User:OsamaK/AlexaBot.js]]. The syntax of the list is:
#     "Example (website) example.com"
# It could optionally include the "local" flag to fetch the local
# Alexa ranking (the one beside the 'Global ranking'):
#     "Example (website) example.com local"

import codecs
import re
import urllib
import sys
import shelve
import time
from datetime import datetime
import json
import urllib2

import pywikibot


class RankingBot(object):
    # Fill in (name of field in template)
    FIELD_NAME = None
    METRIC_NAME = None
    WEBSITES_LIST_PAGE = 'User:OsamaK/AlexaBot.js'
    EDIT_SUMMARY = "Bot: Updating Alexa ranking ([[User talk:" \
                   "OsamaK/AlexaBot.js|Help get more pages covered]])"

    def __init__(self):
        sys.stdout = codecs.getwriter('utf8')(sys.stdout)
        self.database = shelve.open('alexa_rankings.db')
        self.now = datetime.now()
        self.month_names = ['January', 'February', 'March', 'April', 'May',
                       'June', 'July', 'August', 'September',
                       'October', 'November', 'December']
        self.site = pywikibot.getSite()

    def get_article_list(self):
        list_regex = '"(.+)" ([^ \n]+)[ ]?(local)?'
        list_page = pywikibot.Page(self.site, self.WEBSITES_LIST_PAGE).get()
        articles_list = re.findall(list_regex, list_page)

        return articles_list

    def get_rankings(self, site_url, key=None):
        '''
        Gets rankings from the webmetric API.

        @param site_url: The website the get the metrics on (i.e. google.com, facebook.com)
        @param key: If the API requires a key (optional)
        @return:
        '''
        raise NotImplementedError('Implement the get_rankings method to fetch the current site rankings from the API')

    def find_difference(self, article_url, new_ranking):
        try:
            old_ranking = self.database[article_url]
        except KeyError: # If the website is newly added.
            old_ranking = 0

        print "New ranking is", new_ranking, "old was", old_ranking

        if old_ranking == 0:
            difference = ""
        elif old_ranking > new_ranking:
            difference = "{{DecreasePositive}} "
        elif old_ranking < new_ranking:
            difference = "{{IncreaseNegative}} "
        elif old_ranking == new_ranking:
            difference = "{{Steady}} "

        return difference

    def save_article(self, article_object, article_text, article_url,
                       old_alexa_field, new_alexa_field, new_ranking):
        article_text = article_text.replace(old_alexa_field, new_alexa_field)
        edit_summery = self.EDIT_SUMMARY

        article_object.put(article_text, comment=edit_summery)

        time.sleep(10)
        self.database[article_url] = new_ranking

    def run(self):
        ranking_field_regex = "\| *%s *= *.+[\|\n]" %(self.FIELD_NAME)
        old_ranking_regex = "\| *%s *= *(.+)[\|\n]" %(self.FIELD_NAME)
        url_field_regex = "\| *url *= *\[.+?[\|\n]"
        reference_regex = "(\<references|\{\{(reference|refs|re|listaref" \
                          "|ref-list|reflist|footnotesmall|reference list" \
                          "|ref list))"

        print "Fetching articles list.."
        articles_list = self.get_article_list()

        if self.database == {}: # If this is the first time.
            print "This seems to be the first time. No difference templete" \
                  " will be added."
            for article in articles_list:
                self.database[str(article[1])] = 0

        for article in articles_list:
            article_name = article[0]
            article_url = str(article[1])

            try:
                article_object = pywikibot.Page(self.site, article_name)
            except UnicodeDecodeError: #FIXME: Unknown error
                continue

            print u"Fetching %s page on pywikibot.." % article_name
            try:
                article_text = article_object.get()
            except pywikibot.NoPage:
                print u"Page %s does not exist." % article_name
                continue
            except pywikibot.IsRedirectPage:
                article_object = article_object.getRedirectTarget()
                article_name = article_object.title()
                if "#" in article_name:
                    print u"Page %s does not exist." % article_name #Skip sections
                    continue
                article_text = article_object.get()                    
                
            if not re.search(reference_regex, article_text, flags=re.IGNORECASE):
                print u"No reference list in", article_name
                continue

            try:
                old_ranks_field = re.findall(ranking_field_regex, article_text)[0]
            except IndexError:
                try:
                    url_field = re.findall(url_field_regex, article_text)[0]
                except IndexError:
                    print u"No url fields in", article_name
                    continue
                old_ranks_field = "| %s = " % self.FIELD_NAME
                article_text = article_text.replace(url_field, url_field + old_ranks_field)

            try:
                ranking_text, site_title, new_ranking = self.get_rankings(article_url)
            except IndexError:
                print "Couldn't find any ranking data on", article_url
                continue

            new_field_ranking = self.find_difference(str(article[1]), ranking_text) + u"%(ranking_text)s ({{as of|%(year)d|%(month)d|%(day)d" \
                                u"|alt=%(month_name)s %(year)d}})<ref name=\"%(field_name)s\">" \
                                u"{{cite web|url= %(url)s |title= %(title)s " \
                                u"| publisher= [[%(metric_name)s]] " \
                                u"|accessdate= %(year)d-%(month)02d-%(day)02d }}</ref>" \
                                u"<!--Updated monthly by OKBot.-->" % \
                             {"ranking_text": ranking_text, "title": site_title, 'field_name': self.FIELD_NAME,
                              'metric_name': self.METRIC_NAME,
                              "url": self.get_human_version(article_url), "year": self.now.year,
                              "month": self.now.month, "day": self.now.day,
                              "month_name": self.month_names[self.now.month-1]}

            try:
                old_field_ranking = re.findall(old_ranking_regex, old_ranks_field)[0]

                # If old_field_ranking is an empty space:
                if not old_field_ranking.strip():
                    raise IndexError
                new_rankings_field = old_ranks_field.replace(old_field_ranking, new_field_ranking)
            except IndexError: # If the rankings field wasn't there or was empty.
                new_rankings_field = old_ranks_field.strip() + " " + new_field_ranking + "\n"

            try:
                self.save_article(article_object, article_text,
                                  article_url, old_ranks_field,
                                  new_rankings_field, new_ranking)
            except pywikibot.IsRedirectPage:
                print u"Weird error on %s. This shouldn't be a " \
                    u"redirect!" % article_name
                continue

        self.database.close()


class SimilarWebBot(RankingBot):
    FIELD_NAME = 'similarweb'
    METRIC_NAME = 'SimilarWeb'


    def get_human_version(self, url):
        return 'http://www.similarweb.com/website/' + url

    def get_rankings(self, site_url, key='b6d8bb9dab3ba57c48bf024cd426b4a7'):
        try:
            req = urllib2.urlopen('http://api.similarweb.com/Site/%s/v1/traffic?Format=JSON&UserKey=%s' %(site_url, key))
            if req:
                resp = req.read()
                similiar_web_rankings = json.loads(resp)
                rank = similiar_web_rankings['GlobalRank']
                return rank, "original-url-todo", rank
        except KeyError:
            raise
        except:
            # TODO: handle
            raise

if __name__ == '__main__':
    try:
        bot = SimilarWebBot()
        bot.run()
    finally:
        pywikibot.stopme()
