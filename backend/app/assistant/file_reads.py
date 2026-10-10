"""Bounded project file access. File descriptors prevent symlink escapes on POSIX."""
import io
import os
import re
import stat
import subprocess
import zipfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path, PurePosixPath
from PIL import Image
from fastapi import HTTPException
from .. import models
from . import schemas as s
from .identity import require_tool_context
from .readonly import page
from .tool_catalog import TOOL_CATALOG

FILE_TOOLS = frozenset(("list_directory", "read_text", "get_media_preview"))
BLOCKED = {".git", ".env", "node_modules", "profiles.json", "deepseek.json", "external_config.json", "hermes-model.json", "library.db"}
SECRET_EXT = {".pem", ".key", ".p12", ".pfx", ".db", ".sqlite", ".sqlite3"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".bmp"}

def clean_parts(relative):
    p=PurePosixPath(relative.replace("\\","/"))
    if p.is_absolute() or ".." in p.parts or any(":" in x or "\x00" in x or x.casefold() in BLOCKED or x.casefold().startswith(".env") for x in p.parts):
        raise HTTPException(403,"assistant_path_outside_root")
    if p.suffix.lower() in SECRET_EXT:
        raise HTTPException(403,"assistant_path_outside_root")
    return p.parts

def root_path(db, folder_id):
    row=db.get(models.Folder,folder_id)
    if not row:
        raise HTTPException(404,"assistant_folder_not_found")
    original=Path(row.path).absolute()
    if any(p.is_symlink() for p in [original,*original.parents]):
        raise HTTPException(403,"assistant_path_outside_root")
    root=original.resolve()
    configured=os.getenv("HE_ASSISTANT_MEDIA_ROOTS", "/mnt/hdd" if os.name != "nt" else str(root))
    allowed=[Path(x).resolve() for x in configured.split(os.pathsep) if x]
    if not any(root.is_relative_to(x) for x in allowed) or root == Path(root.anchor):
        raise HTTPException(403,"assistant_path_outside_root")
    if not root.is_dir():
        raise HTTPException(404,"assistant_file_unavailable")
    return root

def resolve_project_path(db, folder_id, relative_path, *, must_exist=True):
    root=root_path(db,folder_id);parts=clean_parts(relative_path);target=root.joinpath(*parts)
    if any(root.joinpath(*parts[:i]).is_symlink() for i in range(1,len(parts)+1)):
        raise HTTPException(403,"assistant_path_outside_root")
    if not target.resolve().is_relative_to(root):
        raise HTTPException(403,"assistant_path_outside_root")
    if must_exist and not target.exists():
        raise HTTPException(404,"assistant_file_unavailable")
    return target

@contextmanager
def open_project(db, folder_id, relative, *, directory=False):
    root=root_path(db,folder_id);parts=clean_parts(relative)
    descriptors=[]
    try:
        if os.name == "nt":
            path=resolve_project_path(db,folder_id,relative)
            fd=os.open(path,os.O_RDONLY)
            descriptors.append(fd)
        else:
            fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);descriptors.append(fd)
            for i,name in enumerate(parts):
                flags=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK
                if directory or i<len(parts)-1:flags|=os.O_DIRECTORY
                fd=os.open(name,flags,dir_fd=fd);descriptors.append(fd)
        mode=os.fstat(fd).st_mode
        if (directory and not stat.S_ISDIR(mode)) or (not directory and not stat.S_ISREG(mode)):
            raise HTTPException(403,"assistant_file_unavailable")
        yield fd
    except OSError:
        raise HTTPException(404,"assistant_file_unavailable") from None
    finally:
        for fd in reversed(descriptors):os.close(fd)

def redact_text(text):
    text=re.sub(r'(?im)^.*(?:password|passwd|secret|token|api[_-]?key|authorization|cookie)["\\'\t ]*[:=].*$',"[已隐藏含凭据的行]",text)
    text=re.sub(r"(?i)(https?://)[^/\s:@]+:[^/\s@]+@",r"\1[已隐藏凭据]@",text)
    text=re.sub(r"(?i)([?&](?:token|key|api_key|auth|password|signature)=)[^&\s]+",r"\1[已隐藏]",text)
    text=re.sub(r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----","[已隐藏私钥]",text,flags=re.S)
    return text

def media_location(db, media_id):
    media=db.get(models.Media,media_id)
    if not media or not media.folder_id or not media.absolute_path:
        raise HTTPException(404,"assistant_media_not_found")
    root=root_path(db,media.folder_id)
    try:relative=Path(media.absolute_path).absolute().relative_to(root).as_posix()
    except ValueError:raise HTTPException(403,"assistant_path_outside_root") from None
    resolve_project_path(db,media.folder_id,relative)
    return media,relative

def image_payload(raw):
    if len(raw)>32*1024*1024:raise HTTPException(413,"assistant_content_too_large")
    try:
        with Image.open(io.BytesIO(raw)) as img:
            if img.width*img.height>40_000_000:raise HTTPException(413,"assistant_content_too_large")
            img.thumbnail((1600,1600));out=io.BytesIO();img.convert("RGB").save(out,format="JPEG",quality=85)
            return out.getvalue(),"image/jpeg"
    except (OSError,ValueError):raise HTTPException(422,"assistant_file_unavailable") from None

def preview_payload(db, media_id, page_index=0):
    media,relative=media_location(db,media_id)
    path=resolve_project_path(db,media.folder_id,relative)
    if media.media_type in ("audio","video") and path.is_file():
        with open_project(db,media.folder_id,relative) as fd:
            input_path="/proc/self/fd/"+str(fd) if os.name != "nt" else str(path)
            args=["ffmpeg","-nostdin","-v","error","-i",input_path,"-t","10"]
            if media.media_type=="video":args += ["-vf","scale=640:-2","-an","-c:v","libx264","-preset","ultrafast","-movflags","frag_keyframe+empty_moov","-f","mp4"]
            else:args += ["-vn","-c:a","libmp3lame","-f","mp3"]
            args += ["-fs","8M","pipe:1"]
            try:
                proc=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=20,check=True,**({"pass_fds":(fd,)} if os.name != "nt" else {}))
            except (OSError,subprocess.SubprocessError):raise HTTPException(503,"assistant_file_unavailable") from None
            return proc.stdout,"video/mp4" if media.media_type=="video" else "audio/mpeg"
    if path.is_dir():
        files=[]
        for base,dirs,names in os.walk(path,followlinks=False):
            dirs[:]=[x for x in dirs if not Path(base,x).is_symlink() and x.casefold() not in BLOCKED]
            for name in names:
                file=Path(base,name)
                if file.suffix.lower() in IMAGE_EXT and not file.is_symlink():files.append(file)
                if len(files)>10000:raise HTTPException(413,"assistant_content_too_large")
        files.sort()
        if page_index>=len(files):raise HTTPException(404,"assistant_file_unavailable")
        with open_project(db,media.folder_id,files[page_index].relative_to(root_path(db,media.folder_id)).as_posix()) as fd:
            return image_payload(os.read(fd,32*1024*1024+1))
    with open_project(db,media.folder_id,relative) as fd:
        if path.suffix.lower() in (".zip",".cbz"):
            with os.fdopen(os.dup(fd),"rb") as handle,zipfile.ZipFile(handle) as z:
                infos=z.infolist()
                if len(infos)>10000 or sum(x.file_size for x in infos)>2*1024**3:raise HTTPException(413,"assistant_content_too_large")
                entries=sorted([x for x in infos if not x.is_dir() and Path(x.filename).suffix.lower() in IMAGE_EXT],key=lambda x:x.filename)
                if page_index>=len(entries):raise HTTPException(404,"assistant_file_unavailable")
                entry=entries[page_index];clean_parts(entry.filename)
                if entry.file_size>32*1024*1024 or entry.file_size>max(1,entry.compress_size)*200:raise HTTPException(413,"assistant_content_too_large")
                return image_payload(z.read(entry))
        return image_payload(os.read(fd,32*1024*1024+1))

def execute_file_read(db,principal,context,name,args):
    require_tool_context(db,principal,context)
    q=TOOL_CATALOG[name].args_type.model_validate(args)
    if name=="list_directory":
        with open_project(db,q.folder_id,q.relative_path,directory=True) as fd:
            location=fd if os.name != "nt" else resolve_project_path(db,q.folder_id,q.relative_path)
            entries=[]
            with os.scandir(location) as scan:
                for e in scan:
                    if len(entries)>=10000:raise HTTPException(413,"assistant_content_too_large")
                    st=e.stat(follow_symlinks=False)
                    entries.append(dict(name=e.name,relative_path=PurePosixPath(q.relative_path,e.name).as_posix(),entry_type="link" if e.is_symlink() else "directory" if e.is_dir(follow_symlinks=False) else "file",size=max(0,st.st_size),modified_at=datetime.utcfromtimestamp(st.st_mtime)))
            entries.sort(key=lambda x:(x["entry_type"]!="directory",x["name"]))
            items=entries[q.offset:q.offset+q.limit]
            for item in items:
                match=db.query(models.Media.id).filter(models.Media.absolute_path==str(root_path(db,q.folder_id)/item["relative_path"])).first()
                item["media_id"]=match[0] if match else None
            result=page(items,len(entries),q)
    elif name=="read_text":
        with open_project(db,q.folder_id,q.relative_path) as fd:
            prefix=os.read(fd,65536)
            if b"PRIVATE KEY-----" in prefix:
                raise HTTPException(403,"assistant_path_outside_root")
            os.lseek(fd,q.offset_bytes,os.SEEK_SET);raw=os.read(fd,32772)
        if b"\x00" in raw:raise HTTPException(422,"assistant_invalid_text")
        chunk=raw[:32768]
        try:text=chunk.decode("utf-8")
        except UnicodeDecodeError as exc:
            if exc.reason=="unexpected end of data" and exc.start>=len(chunk)-3:
                chunk=chunk[:exc.start];text=chunk.decode("utf-8")
            else:raise HTTPException(422,"assistant_invalid_text") from None
        text=redact_text(text)
        # Bound JSON expansion while preserving a continuation into the source.
        while len(__import__("json").dumps(text,ensure_ascii=False).encode())>45000:
            chunk=chunk[:len(chunk)//2]
            try: text=redact_text(chunk.decode("utf-8"))
            except UnicodeDecodeError as exc:
                chunk=chunk[:exc.start];text=redact_text(chunk.decode("utf-8"))
        more=len(raw)>len(chunk)
        result=dict(folder_id=q.folder_id,relative_path=q.relative_path,text=text,offset_bytes=q.offset_bytes,next_offset_bytes=q.offset_bytes+len(chunk) if more else None,truncated=more)
    else:
        media,_=media_location(db,q.media_id)
        result=dict(media_id=media.id,media_type=media.media_type,page_index=q.page_index if media.media_type=="manga" else None,page_count=media.page_count,preview_path=f"/assistant/media/{media.id}/preview?page_index={q.page_index}",analysis_supported=False,analysis_performed=False,notice="可在网页查看预览；当前模型未分析文件内容。音视频预览为前 10 秒。")
    return s.RESULT_TYPES[name].model_validate(result).model_dump(mode="json")
