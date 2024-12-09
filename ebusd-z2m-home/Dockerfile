# For more information, please refer to https://aka.ms/vscode-docker-python
FROM python:3-slim-bookworm AS python-requirements-libs


WORKDIR /user/src/app 
COPY libs/libs.py . 
COPY requirements.txt .
RUN pip install -r requirements.txt --user 


FROM python-requirements-libs AS frontend
WORKDIR /user/src/app 
COPY frontend/. .
CMD ["python","-u","web.py"]
EXPOSE 5002

FROM python-requirements-libs AS controller
WORKDIR /user/src/app 
COPY controler/. .
CMD ["python","-u","z2m_monitor.py"]

FROM python-requirements-libs AS watcher
WORKDIR /user/src/app 
COPY watcher/. .
CMD ["python","-u","ebusd_monitor.py"]
