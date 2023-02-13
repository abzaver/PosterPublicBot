import os
import sqlite3
import time
import datetime
from PIL import Image
import imagehash
from hexhamming import hamming_distance_string
import json

DATABASE_NAME = 'search_img.db'


def create_or_open_db(db_name):
    table_name = 'images'
    try:
        db_connection = sqlite3.connect(db_name)
        sqlite_create_table_query = f'''CREATE TABLE IF NOT EXISTS {table_name} (
                                    id        INTEGER  PRIMARY KEY AUTOINCREMENT
                                                       NOT NULL,
                                    chat_id   TEXT     NOT NULL,
                                    pHash     INTEGER  NOT NULL,
                                    msg_id    TEXT     NOT NULL,
                                    timestamp DATETIME NOT NULL,
                                    file_name TEXT     NOT NULL
                                    );'''

        cursor = db_connection.cursor()
        cursor.execute(sqlite_create_table_query)
        db_connection.commit()
        cursor.close()

    except sqlite3.Error as error:
        print("Ошибка при подключении к sqlite", error)
        return False
    finally:
        return db_connection


def add_img_to_db(db_connection, tuple_images_data):
    try:
        cursor = db_connection.cursor()

        sqlite_insert_with_param = """INSERT INTO images
                              (chat_id, pHash, msg_id, timestamp, file_name)
                              VALUES (?, ?, ?, ?, ?);"""

        cursor.executemany(sqlite_insert_with_param, tuple_images_data)
        db_connection.commit()

        cursor.close()

    except sqlite3.Error as error:
        print("Ошибка при работе с SQLite", error)
        return False
    finally:
        return True


def add_images(db_connection, image_paths):
    data_tuple_list = []
    for image_type, image_name in image_paths.items():
        image_hash = imagehash.phash(Image.open(image_name))
        data_tuple_list.append(tuple((image_type, str(image_hash), './{}'.format(image_name), datetime.datetime.now())))

    return add_img_to_db(db_connection, data_tuple_list)


def search_by_image(db_connection, image_path, dist=20):
    curr_time = time.time_ns()
    searched_image_hash = imagehash.phash(Image.open(image_path))
    print(f'searched image hash: {searched_image_hash} filename {image_path}')
    try:
        db_connection.create_function("hexhammdist", 2, hamming_distance_string)
        cursor = db_connection.cursor()

        sqlite_select_query = f'select *, hexhammdist(phash, ?) as hd from images where hd <= ? order by hd;'
        cursor.execute(sqlite_select_query, [str(searched_image_hash), dist])
        records = cursor.fetchall()
        for record in records:
            # print(record)
            print(
                f'hash in db: {record[2]} hash searched image: {searched_image_hash} humming dist: {record[6]}  msg_id: {record[3]} ')
        cursor.close()
        print("затраченное время (мс): ", (time.time_ns() - curr_time) / 1000000)

    except sqlite3.Error as error:
        print("Ошибка при работе с SQLite", error)
        return False
    finally:
        return True


def parse_telegram_from_json(db_connection, filename):
    data_tuple_list = []
    curr_time = time.time_ns()
    print('Начали парсить...')
    with open(filename, 'r', encoding='utf-8') as import_file:
        chat_data = json.load(import_file)
        json.dumps(chat_data, indent=4, sort_keys=False, ensure_ascii=False)
        if 'id' in chat_data:
            chat_id = chat_data['id']
        for message in chat_data['messages']:
            if 'photo' in message:
                img_filename = message['photo']
                image_hash = imagehash.phash(Image.open(f"{os.path.normpath(os.path.dirname(filename))}/{img_filename}"))
            else:
                continue
            if 'id' in message:
                msg_id = message['id']
            if 'date_unixtime' in message:
                timestamp = message['date_unixtime']
            data_tuple_list.append(tuple((chat_id, str(image_hash), msg_id, int(timestamp), img_filename)))
        print('Закончили парсить, заняло (мс): ', (time.time_ns() - curr_time) / 1000000)
        print('Начали добавлять...')
        curr_time = time.time_ns()
        if add_img_to_db(db_connection, data_tuple_list):
            print('Закончили добавлять, заняло (мс): ', (time.time_ns() - curr_time) / 1000000)
        else:
            print('Но что-то пошло не так...')

if __name__ == '__main__':
    db_connection = create_or_open_db(DATABASE_NAME)
    #search_by_image(db_connection, r'./ChatExport_2023-02-10/photos/photo_3158@02-01-2023_22-05-00.jpg', 18)
    #search_by_image(db_connection,'thorston-original.jpg', 18)
    parse_telegram_from_json(db_connection, r'./ChatExport_2023-02-10/result.json')
    db_connection.close()




