import logging
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup as bs
from endpoints import TPSTUDENT_URL, NOTICEBOARD_URL, NOTICES_URL, ATTACHMENT_URL, NOTICE_CONTENT_URL


LAST_NOTICES_CHECK_COUNT = 30

    
def fetch(headers, session, ssoToken, notice_db):
    print('[FETCHING NOTICES]', flush=True)
    try:
        r = session.post(TPSTUDENT_URL, data=dict(ssoToken=ssoToken, menu_id=11, module_id=26), headers=headers)
        r = session.get(NOTICEBOARD_URL, headers=headers)
        r = session.get(NOTICES_URL, headers=headers)
    except Exception as e:
        logging.error(f" Failed to navigate to Noticeboard ~ {str(e)}")
        return []

    try:
        soup = bs(r.text, features="xml")
        xml = soup.prettify().encode('utf-8')
        root = ET.fromstring(xml)
    except Exception as e:
        logging.error(f" Failed to extract data from Noticeboard ~ {str(e)}")
        return []

    latest_X_notices = []
    for i, row in enumerate(root.findall('row')):
        if i >= LAST_NOTICES_CHECK_COUNT:
            break

        # Safe extraction with null checks
        try:
            id_cell = row.find('cell[1]')
            if id_cell is None or id_cell.text is None:
                logging.warning(f" Skipping row {i}: Missing ID cell")
                continue
            id_ = id_cell.text.strip()

            year_cell = root.findall('row')[0].find('cell[8]')
            if year_cell is None or year_cell.text is None:
                logging.warning(f" Skipping row {i}: Missing year cell")
                continue
            year = year_cell.text.split('"')[1].strip()

            # Extract other fields with safe null checks
            time_cell = row.find('cell[7]')
            time_text = time_cell.text.strip() if time_cell is not None and time_cell.text is not None else ''
            
            type_cell = row.find('cell[2]')
            type_text = type_cell.text.strip() if type_cell is not None and type_cell.text is not None else ''
            
            subject_cell = row.find('cell[3]')
            subject_text = subject_cell.text.strip() if subject_cell is not None and subject_cell.text is not None else ''
            
            company_cell = row.find('cell[4]')
            company_text = company_cell.text.strip() if company_cell is not None and company_cell.text is not None else ''

            notice = {
                'UID': f'{id_}_{year}',
                'Time': time_text,
                'Type': type_text,
                'Subject': subject_text,
                'Company': company_text,
            }
        except Exception as e:
            logging.error(f" Failed to parse row {i}: {str(e)}")
            continue

        # Handling Body
        try:
            body_data = parse_body_data(session, year, id_)
            notice['BodyData'] = body_data
        except Exception as e:
            logging.error(f" Failed to parse notice body ~ {str(e)}")
            break

        # Handling attachment
        try:
            attachment = parse_attachment(session, year, id_)
            if attachment:
                notice['Attachment'] = attachment
        except Exception as e:
            logging.error(f" Failed to parse attachment ~ {str(e)}")
            break

        latest_X_notices.append(notice)
    
    # This is done to reduce DB queries
    # Get all first X notices from ERP in latest_notices
    # Check if these notices exist in the DB using their UIDs in a single query
    # Get new notice uids, filter out new notices from latest_notices based on uids
    new_notices, modified_notices = notice_db.find_to_send_notices(latest_X_notices)

    # Log new notices
    for notice in new_notices:
        logging.info(f" [NEW NOTICE]: #{notice['UID'].split('_')[0]} | {notice['Type']} | {notice['Subject']} | {notice['Company']} | {notice['Time']}")

    # Log modified notices
    for notice in modified_notices:
        logging.info(f" [MODIFIED NOTICE]: #{notice['UID'].split('_')[0]} | {notice['Type']} | {notice['Subject']} | {notice['Company']} | {notice['Time']}")

    notices = new_notices + modified_notices

    return notices


def parse_body_data(session, year, id_):
    content = session.get(NOTICE_CONTENT_URL.format(year, id_))
    content_html = bs(content.text, 'html.parser')
    body_data = bs.find_all(content_html, 'div', {'id': 'printableArea'})[0]

    return body_data


def parse_attachment(session, year, id_):
    stream = session.get(ATTACHMENT_URL.format(year, id_), stream=True)
    attachment = b''
    for chunk in stream.iter_content(4096):
        attachment += chunk
    
    return attachment

