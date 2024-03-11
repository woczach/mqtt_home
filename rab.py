import pika

#connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
#channel = connection.channel()


def main():
    connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
    channel = connection.channel()

#    channel.queue_declare(queue='all')

    def callback(ch, method, properties, body):
        print(f"-> Received {body}")
        #print(f"-> prop {properties}")
        print(f"-> ch {ch}")
        print(f"->  met {method.routing_key}")
        print()

    channel.basic_consume(queue='all', on_message_callback=callback, auto_ack=True)

    print(' [*] Waiting for messages. To exit press CTRL+C')
    channel.start_consuming()

main()
