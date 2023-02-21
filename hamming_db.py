import os
import sqlite3
import time
import datetime
from PIL import Image
import imagehash
from hexhamming import hamming_distance_string
import json
import ffmpeg
import logging

from numpy import tile

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


DATABASE_NAME = 'search_img.db'
ANIMATION_TILE_OUT_FILENAME = './data/animation-tile.png'

def create_or_open_db(db_name):
    try:
        db_connection = sqlite3.connect(db_name)
        sqlite_create_table_query = f'''CREATE TABLE IF NOT EXISTS images (
                                        id        INTEGER  PRIMARY KEY AUTOINCREMENT
                                                           NOT NULL,
                                        chat_id   INTEGER  NOT NULL,
                                        pHash     INTEGER  NOT NULL,
                                        msg_id    INTEGER  NOT NULL,
                                        timestamp DATETIME NOT NULL,
                                        file_name TEXT     NOT NULL
                                    );

                                    CREATE TABLE IF NOT EXISTS groups_and_chats (
                                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                                        chat_id     INTEGER UNIQUE ON CONFLICT REPLACE,
                                        chat_name   TEXT,
                                        chat_type   TEXT
                                    );'''

        cursor = db_connection.cursor()
        cursor.executescript(sqlite_create_table_query)
        db_connection.commit()
        cursor.close()

    except sqlite3.Error as error:
        print("Ошибка при подключении к sqlite", error)
        return False
    finally:
        return db_connection


def add_chat_to_db(db_connection, tuple_chat_data):
    try:
        cursor = db_connection.cursor()

        sqlite_insert_with_param = """INSERT INTO groups_and_chats
                              (chat_id, chat_name, chat_type)
                              VALUES (?, ?, ?);"""

        cursor.execute(sqlite_insert_with_param, tuple_chat_data)
        db_connection.commit()

        cursor.close()

    except sqlite3.Error as error:
        print("Ошибка при работе с SQLite", error)
        return False
    finally:
        return True


def add_images_by_hash(db_connection, tuple_hash_images_data):
    try:
        cursor = db_connection.cursor()

        sqlite_insert_with_param = """INSERT INTO images
                              (chat_id, pHash, msg_id, timestamp, file_name)
                              VALUES (?, ?, ?, ?, ?);"""

        cursor.executemany(sqlite_insert_with_param, tuple_hash_images_data)
        db_connection.commit()

        cursor.close()

    except sqlite3.Error as error:
        print("Ошибка при работе с SQLite", error)
        return False
    finally:
        return True


def add_images_by_path(db_connection, tuple_path_images_data):
    data_tuple_list = []
    for image_tuple in tuple_path_images_data:
        image_hash = imagehash.phash(Image.open(image_tuple[1]))
        data_tuple_list.append(tuple((image_tuple[0], str(image_hash), image_tuple[2], image_tuple[3], '')))

    return add_images_by_hash(db_connection, data_tuple_list)


def search_by_image(db_connection, image_path, dist=20):
    searched_image_hash = imagehash.phash(Image.open(image_path))
    return search_by_image_hash(db_connection, searched_image_hash, dist)


def search_by_image_hash(db_connection, image_hash, dist=20):
    db_connection.create_function("hexhammdist", 2, hamming_distance_string)
    cursor = db_connection.cursor()

    sqlite_select_query = f'select *, hexhammdist(phash, ?) as hd from images where hd <= ? order by hd;'
    cursor.execute(sqlite_select_query, [str(image_hash), dist])
    return cursor.fetchall()

def search_by_image_result_text(db_connection, image_path, dist=20):
    curr_time = time.time_ns()
    records = search_by_image(db_connection, image_path, dist)
    for record in records:
        # print(record)
        print(
            f'hash in db: {record[2]} hash searched image: {imagehash.phash(Image.open(image_path))} humming dist: {record[6]}  msg_id: {record[3]} ')
    print("затраченное время (мс): ", (time.time_ns() - curr_time) / 1000000)


def parse_telegram_from_json(db_connection, filename):
    imgs_tuple_list = []
    curr_time = time.time_ns()
    print('Начали парсить...')
    with open(filename, 'r', encoding='utf-8') as import_file:
        chat_data = json.load(import_file)
        json.dumps(chat_data, indent=4, sort_keys=False, ensure_ascii=False)
        if 'id' in chat_data:
            chat_id = chat_data['id']
        if 'name' in chat_data:
            chat_name = chat_data['name']
        if 'type' in chat_data:
            chat_type = chat_data['type']
        if chat_id:
            add_chat_to_db(db_connection, [chat_id, chat_name, chat_type])

        for message in chat_data['messages']:
            if 'photo' in message:
                img_filename = message['photo']
                image_hash = imagehash.phash(
                    Image.open(f"{os.path.normpath(os.path.dirname(filename))}/{img_filename}"))
            else:
                continue
            if 'id' in message:
                msg_id = message['id']
            if 'date_unixtime' in message:
                timestamp = message['date_unixtime']
            imgs_tuple_list.append(tuple((chat_id, str(image_hash), msg_id, int(timestamp), img_filename)))
        print('Закончили парсить, заняло (мс): ', (time.time_ns() - curr_time) / 1000000)
        print('Начали добавлять...')
        curr_time = time.time_ns()
        if add_images_by_hash(db_connection, imgs_tuple_list):
            print('Закончили добавлять, заняло (мс): ', (time.time_ns() - curr_time) / 1000000)
        else:
            print('Но что-то пошло не так...')


def animation_to_hash(in_filename):
    probe = ffmpeg.probe(in_filename)
    frames = 0
    for stream in probe['streams']:
        if stream['codec_type'] == 'video':
            frames = int(probe['streams'][int(stream['index'])]['nb_frames']) // 6
            break

    (
        ffmpeg
        .input(in_filename)
        .filter('scale', 640, -1)
        .filter('select', 'eq(n,{})+eq(n,{})+eq(n,{})+eq(n,{})+eq(n,{})+eq(n,{})'.format(0, frames, frames * 2, frames * 3, frames * 4, frames * 5))
        .filter('tile', '3x2')
        .output(ANIMATION_TILE_OUT_FILENAME, vframes=4, vsync=0)
        .overwrite_output()
        .run(capture_stdout=True, capture_stderr=True)
    )
    return imagehash.phash(Image.open(ANIMATION_TILE_OUT_FILENAME))


if __name__ == '__main__':
    print(animation_to_hash('./data/animation_to_search'))
    #db_connection = create_or_open_db(DATABASE_NAME)
    # search_by_image_result_text(db_connection, r'./ChatExport_2023-02-10/photos/photo_3158@02-01-2023_22-05-00.jpg', 18)
    # search_by_image_result_text(db_connection,'thorston-original.jpg', 18)
    # search_by_image_result_text(db_connection, 'img_to_search', 18)
    #parse_telegram_from_json(db_connection, r'../ImgSearchSQLite/ChatExport_2023-02-10/result.json')
    #db_connection.close()
