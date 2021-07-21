import boto3
import logging
import os
import time

logger = logging.getLogger()
log_level = os.getenv('LOG_LEVEL', 'INFO')
logger.setLevel(logging.getLevelName(log_level))
org = boto3.client('organizations')
licmgn = boto3.client('license-manager')
TagKey = os.environ['Organizations_Tag']
value = ''

def get_grant_byname(GrantName,LicenseArn):
    GrantArn = 'null'
    grantresponse = licmgn.list_distributed_grants(Filters=[{'Name': 'LicenseArn','Values': [LicenseArn,]},],)
    for response in grantresponse['Grants']:
        if response['GrantName'] == GrantName:
            if response['GrantStatus'] == 'ACTIVE':
                GrantArn = response['GrantArn']
                break
    return GrantArn

def update_one_account(account,value):
    if value == "false":
        try:
            licenses = licmgn.list_received_licenses()
        except Exception as error:
            logging.info(f"Could not retrieve licenses from Licence Manager - Error: {error}")         
        for license in licenses['Licenses']:
            if license['Status'] == 'AVAILABLE':
                grant = get_grant_byname(account,license['LicenseArn'])
                version = licmgn.get_grant(GrantArn=grant)
                try:
                    licmgn.delete_grant(
                    GrantArn=grant,
                    Version=version['Grant']['Version'],
                    StatusReason='Licence Automation')
                    logging.info(f"Removed grant: {grant} for license: {license['LicenseArn']}")
                except Exception as error:
                    logging.info(f"Could not remove grant: {grant} for license: {license['LicenseArn']} - Error: {error}")
    if value == "true":
        try:
            licenses = licmgn.list_received_licenses()
        except Exception as error:
            logging.info(f"Could not retrieve licenses from Licence Manager - Error: {error}")         
        for license in licenses['Licenses']:
            if license['Status'] == 'AVAILABLE':
                try:
                    grant = get_grant_byname(account,license['LicenseArn'])
                    if grant == 'null':
                        grant = licmgn.create_grant(
                        GrantName=account,
                        LicenseArn=license['LicenseArn'],
                        Principals=list(f"arn:aws:iam::{account}:root".split(" ")),
                        HomeRegion=license['HomeRegion'],
                        ClientToken=str(time.time()),
                        AllowedOperations=['CheckoutLicense','ListPurchasedLicenses', 'CheckInLicense'])
                        licmgn.create_grant_version(
                        GrantArn=grant['GrantArn'],
                        GrantName=account,
                        ClientToken=str(time.time()),
                        Status='ACTIVE')
                        logging.info(f"Shared license: {license['LicenseArn']} with account: {account}")
                    else:
                        logging.info(f"License: {license['LicenseArn']} already shared with account: {account}")
                except Exception as error:
                    logging.info(f"Could not share license: {license['LicenseArn']} with account: {account} - Error: {error}")


def update_all_accounts():
    try:
        paginator = org.get_paginator('list_accounts')
        page_iterator = paginator.paginate()
        AccMpLicences = {}
        AccMpLicenseTrue = []
        AccMpLicenseFalse = []
        for page in page_iterator:
            for acct in page['Accounts']:
                if acct['Status'] == 'SUSPEND':
                    tags = org.list_tags_for_resource(ResourceId=acct['Id'])
                    for item in tags['Tags']:
                        ctlist = list(item.values())
                        if TagKey in ctlist:
                            if 'true' in ctlist:
                                AccMpLicenseFalse.append(acct['Id'])
                if acct['Status'] == 'ACTIVE':
                    tags = org.list_tags_for_resource(ResourceId=acct['Id'])
                    for item in tags['Tags']:
                        ctlist = list(item.values())
                        if TagKey in ctlist:
                            if 'true' in ctlist:
                                AccMpLicenseTrue.append(acct['Id'])
                            elif 'false' in ctlist:
                                AccMpLicenseFalse.append(acct['Id'])
        AccMpLicences.setdefault('Active',  []).extend(AccMpLicenseTrue)
        AccMpLicences.setdefault('Deactivated',  []).extend(AccMpLicenseFalse)
    except Exception as error:
        logging.info(f"Could not retrieve account list from Organizations - Error: {error}")
    try:
        licenses = licmgn.list_received_licenses()
    except Exception as error:
        logging.info(f"Could not retrieve licenses from Licence Manager - Error: {error}")
    for license in licenses['Licenses']:
        if license['Status'] == 'AVAILABLE':
            license_grants = licmgn.list_distributed_grants(Filters=[{'Name': 'LicenseArn','Values': [license['LicenseArn'],]},],)
            active_grants = []
            deleted_grants = []
            for current_grant in license_grants['Grants']:
                if current_grant['GrantStatus'] == 'ACTIVE':
                    active_grants.append(current_grant['GrantName'])
                if current_grant['GrantStatus'] != 'ACTIVE':
                    deleted_grants.append(current_grant['GrantName'])
            to_be_deleted = []
            to_be_created = []
            logging.info(license['LicenseName'])
            for account in AccMpLicences['Active']:
                if account in active_grants:
                    logging.info(f"{account} - Nothing to do")
                if account in deleted_grants:
                    logging.info(f"Add {account} to list: to_be_created")
                    to_be_created.append(account)
                else:
                    logging.info(f"Add {account} to list: to_be_created")
                    to_be_created.append(account)
            for account in AccMpLicences['Deactivated']:
                if account in active_grants:
                    arn = get_grant_byname(account,license['LicenseArn'])
                    logging.info(f"Add {account} - grant {arn} to list: to_be_deleted")
                    to_be_deleted.append(arn)
                if account in deleted_grants:
                    logging.info(f"{account} - Nothing to do")
            if to_be_created == []:
                logging.info(f"No new Accounts where license: {license['LicenseArn']} needs to be shared with.")
            else:
                for account in to_be_created:
                    try:
                        grant = get_grant_byname(account,license['LicenseArn'])
                        if grant == 'null':
                            grant = licmgn.create_grant(
                            GrantName=account,
                            LicenseArn=license['LicenseArn'],
                            Principals=list(f"arn:aws:iam::{account}:root".split(" ")),
                            HomeRegion=license['HomeRegion'],
                            ClientToken=str(time.time()),
                            AllowedOperations=['CheckoutLicense','ListPurchasedLicenses', 'CheckInLicense'])
                            licmgn.create_grant_version(
                            GrantArn=grant['GrantArn'],
                            GrantName=account,
                            ClientToken=str(time.time()),
                            Status='ACTIVE')
                            logging.info(f"Shared license: {license['LicenseArn']} with account: {account}")
                        else:
                            logging.info(f"License: {license['LicenseArn']} already shared with account: {account}")
                    except Exception as error:
                        logging.info(f"Could not share license: {license['LicenseArn']} with account: {account} - Error: {error}")
            if to_be_deleted == []:
                logging.info(f"No grants to be deleted for license: {license['LicenseArn']}.")
            else:
                for grant in to_be_deleted:
                    try:
                        version = licmgn.get_grant(GrantArn=grant)
                        licmgn.delete_grant(
                        GrantArn=grant,
                        Version=version['Grant']['Version'],
                        StatusReason='Licence Automation')
                        logging.info(f"Removed grant: {grant} for license: {license['LicenseArn']}")
                    except Exception as error:
                        logging.info(f"Could not remove grant: {grant} for license: {license['LicenseArn']} - Error: {error}")

def lambda_handler(event, _context):
    print(f"Got event: {event}")
    if event['detail']['eventName'] == "TagResource":
        value = ''
        account = event['detail']['requestParameters']['resourceId']
        for tag in event['detail']['requestParameters']['tags']:
            ctlist = list(tag.values())
            if TagKey in ctlist:
                if 'true' in ctlist:
                    value = 'true'
                else:
                    value = 'false'
        if value == 'true':
            logging.info(f"Received Event from CloudTrail: TagResource - Update one account with Value: {value}")
            update_one_account(account,value)
            logging.info(f"Received Event from CloudTrail: TagResource - Update one account with Value: {value}")
        elif value == 'false':
            update_one_account(account,value)
        else:
            logging.info(f"{tag} - not the right tag")
    if event['detail']['eventName'] == "ListReceivedGrants":
        logging.info(f"Received Event from CloudTrail: ListReceivedGrants - Update all accounts")
        update_all_accounts()
    if event['detail']['eventName'] == "Initial":
        logging.info(f"Received Initial event - Update all accounts")
        update_all_accounts()