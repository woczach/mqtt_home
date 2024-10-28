# For more information, please refer to https://aka.ms/vscode-docker-python
FROM python:3.12

WORKDIR /user/src/app 



# Install pip requirements

COPY . . 




#RUN  python -m pip install --upgrade pip
#RUN pip install -r requirements.txt --user 


CMD ["python","-u","web.py"]
#ENTRYPOINT ["python", "massarchive.py"] 

EXPOSE 5002
