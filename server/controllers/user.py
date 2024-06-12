import os

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from server.database import SessionLocal
from server.database.user import get_user_by_openid, update_session_key, create_user
from config import CONFIG
from log import logger
from datetime import timedelta, datetime
import requests
from sqlalchemy.orm import Session
import base64
import json
from Crypto.Cipher import AES
from jose import JWTError, jwt


SECRET_CONFIG = CONFIG.get("secret", {})
SECRET_KEY = SECRET_CONFIG.get("secret_key", "")
ALGORITHM = SECRET_CONFIG.get("algorithm", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = SECRET_CONFIG.get("expire_time", 1440)

WX_CONFIG = CONFIG.get("weixin", {})
APP_ID = WX_CONFIG.get("app_id", "")
APP_SECRET = WX_CONFIG.get("app_secret", "")


if "SECRET_KEY" in os.environ:
    SECRET_KEY = os.environ.get("SECRET_KEY")


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_access_token(data: dict) -> str:
    """
    生成access token
    :param data: 加密的内容
    :return: (str)access token
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="无法验证令牌",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        openid: str = payload.get("openid")
        if openid is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = get_user_by_openid(db, openid=openid)
    if user is None:
        raise credentials_exception
    return user


def get_session(code: str):
    """
    通过wx_code获取openid和session_key
    """
    url = "https://api.weixin.qq.com/sns/jscode2session"
    params = {
        "appid": APP_ID,
        "secret": APP_SECRET,
        "js_code": code,
        "grant_type": "authorization_code",
    }
    try:
        res = requests.get(url=url, params=params, verify=False)
        if res.status_code != 200:
            raise Exception(f"code: {res.status_code}")
        data = res.json()
        if data.get("errcode", 0) != 0:
            raise Exception(f'errcode: {data.get("errcode", -2)}, errmsg: {data.get("errmsg", "none")}')
        openid = data.get("openid", None)
        session_key = data.get("session_key", None)
        return openid, session_key
    except Exception as e:
        logger.warning(f"get_session fail: {e}")
        raise e


class WXBizDataCrypt:
    def __init__(self, appId, sessionKey):
        self.appId = appId
        self.sessionKey = sessionKey

    def decrypt(self, encryptedData, iv):
        # base64 decode
        sessionKey = base64.b64decode(self.sessionKey)
        encryptedData = base64.b64decode(encryptedData)
        iv = base64.b64decode(iv)

        cipher = AES.new(sessionKey, AES.MODE_CBC, iv)

        decrypted = json.loads(self._unpad(cipher.decrypt(encryptedData)))

        if decrypted['watermark']['appid'] != self.appId:
            raise Exception('Invalid Buffer')

        return decrypted

    def _unpad(self, s):
        return s[:-ord(s[len(s) - 1:])]


def decrypt(data, key, iv):
    pc = WXBizDataCrypt(APP_ID, key)
    return pc.decrypt(data, iv)


def user_login(session: Session, code: str, encrypt_data: str, iv: str) -> str:
    """
    用户登录，更新session_key
    :param session: 数据库对象
    :param code: wx code
    :param encrypt_data: 加密的用户数据
    :param iv: 解密偏移量
    :return: openid
    """
    openid, session_key = get_session(code)
    user = get_user_by_openid(session, openid)
    if user:  # 用户存在
        update_session_key(session, user.openid, session_key)
    else:
        user_info = decrypt(encrypt_data, session_key, iv)
        create_user(
            session=session,
            openid=openid,
            session_key=session_key,
            nick_name=user_info.get("nickName"),
            avatar_url=user_info.get("avatarUrl"),
        )
    return openid




