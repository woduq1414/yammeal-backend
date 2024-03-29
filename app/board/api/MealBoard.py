import firebase_admin
import marshmallow
import os
from PIL import Image
import uuid
from app.board.form import MealBoardSchema, MealBoardGetListSchema
from app.common.decorator import login_required, return_500_if_errors
from app.common.function import get_day_meal, get_identify
from app.db import *
from flask_restful import Resource, reqparse
import bcrypt
from marshmallow import Schema, fields, pprint, validate
from app.students.form import *
from flask import request, g, abort
import requests
import json
from app.common.function import *

from datetime import datetime
from sqlalchemy import func, desc

from app.scheduler import sched
from app.redis import rd
import datetime, time

class MealBoard(Resource):
    @return_500_if_errors
    def get(self):
        args = request.args
        print(args)
        try:

            args = MealBoardGetListSchema().load(args)
        except marshmallow.exceptions.ValidationError as e:
            print(e.messages)
            return {"message": "파라미터 값이 유효하지 않습니다."}, 400

        if args["limit"] * (args["page"] - 1) < 0:
            return {"message": "파라미터 값이 유효하지 않습니다."}, 400

        post_rows = db.session.query(MealBoard, func.count(MealBoardLikes.like_seq).label("like_count")).outerjoin(
            MealBoardLikes,
            MealBoard.post_seq == MealBoardLikes.post_seq).filter(
            MealBoard.banned == False).group_by(MealBoard.post_seq).order_by(desc(MealBoard.post_seq)).limit(
            args["limit"]).offset(
            args["limit"] * (args["page"] - 1)).all()

        #
        # post_rows = MealBoard.query.filter_by(banned=False).limit(args["limit"]).offset(
        #     args["limit"] * args["page"]).all()

        if len(post_rows) == 0:
            return {
                       "message": "글을 찾을 수 없습니다."
                   }, 404

        return {
                   "data": [{
                       "nickname": post_row.MealBoard.student.nickname,
                       "postSeq": post_row.MealBoard.post_seq,
                       "title": post_row.MealBoard.title,
                       "post_date": str(post_row.MealBoard.post_date),
                       "image_url": post_row.MealBoard.image_url,
                       "like_count": post_row.like_count,
                       "views": post_row.MealBoard.views,
                   } for post_row in post_rows]
               }, 200

    @return_500_if_errors
    @login_required
    def post(self):
        student_id = g.user_id

        try:
            args = json.loads(request.form.get('jsonRequestData'))
        except Exception as e:
            print(request.form.get('jsonRequestData'))
            return {"message": "파라미터 값이 유효하지 않습니다."}, 400

        # print(args)
        try:

            args = MealBoardSchema().load(args)
        except marshmallow.exceptions.ValidationError as e:
            print(e.messages)
            return {"message": "파라미터 값이 유효하지 않습니다."}, 400
        # print(args)

        image_file = request.files['imageFile']
        image_file_extension = os.path.splitext(image_file.filename)[1]
        if image_file_extension not in [".jpg", ".png", ".jpeg"]:
            return {"message": "이미지 파일만 업로드 가능합니다."}, 400

        print(image_file)
        print(image_file_extension)
        image = Image.open(image_file)

        def get_absoulute_path(path):
            script_dir = os.path.dirname(__file__)  # <-- absolute dir the script is in
            rel_path = path
            abs_file_path = os.path.join(script_dir, rel_path)
            return abs_file_path

        image.save(get_absoulute_path("./temp/image.jpg"), quality=85, optimize=True)

        student, school = \
            get_identify() or None, None
        if student is None: return {"message": "올바르지 않은 회원 정보입니다."}, 401

        lunch_meal_data = get_day_meal(school, args["menu_date"], target_time=args["menu_time"])

        bucket = firebase_admin.storage.bucket(name="meal-project-fa430.appspot.com", app=None)
        # bucket.put(image_file)
        blob = bucket.blob(f"user_images/meal/{student.nickname}_{uuid.uuid1()}{image_file_extension}")
        with open(get_absoulute_path("./temp/image.jpg"), "rb") as f:
            blob.upload_from_file(file_obj=f, content_type='image/jpeg')
            blob.make_public()

        image_url = blob.public_url

        post_row = MealBoard(
            school=school,
            student=student,
            menus=lunch_meal_data,
            image_url=image_url,
            menu_date=args["menu_date"],
            post_date=datetime.datetime.now(),
            title=args["title"],
            content=args["content"],
            banned=False,
        )
        db.session.add(post_row)
        db.session.commit()

        return {
                   "message": "정상적으로 처리되었습니다."
               }, 200