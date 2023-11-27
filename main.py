from flask import Flask, render_template, request, redirect, url_for, jsonify
from replit import db
import uuid
import openai
import time
from threading import Thread

app = Flask(__name__)


@app.route('/')
def index():
  return render_template('index.html')


@app.route('/submit_case', methods=['POST'])
def submit_case():
  problem = request.form['problem']
  case = request.form['case']
  # Generate a unique ID for the entry
  unique_id = str(uuid.uuid4())
  if db:
    db[unique_id] = {'problem': problem, 'case': case, 'status': 'pending'}
  else:
    return "Database not found", 500

  # Redirect to a unique URL
  return redirect(url_for('share_case', case_id=unique_id))


@app.route('/share_case/<case_id>')
def share_case(case_id):
  return render_template('share.html', case_id=case_id)


@app.route('/case/<case_id>', methods=['GET', 'POST'])
def view_case(case_id):
  if not db:
    return "Database not found", 500

  case_data = db.get(case_id)

  if not case_data:
    return "Case not found", 404

  if request.method == 'POST':
    response = request.form['response']
    if not case_data.get('response'):
      case_data['response'] = response
    else:
      return "Case already solved", 400
    return redirect(url_for('judge_case', case_id=case_id))

  return render_template('response.html',
                         problem=case_data['problem'],
                         case_id=case_id)


def process_judgement(case_id):
  if not db:
    return "Database not found", 500

  case_data = db.get(case_id)
  if not case_data:
    return "Case not found", 404

  problem = case_data['problem']
  case = case_data['case']
  response = case_data['response']

  # Content for OpenAI API
  content = f"Overview: {problem}\n\nPlaintiff Argument: {case}\n\nDefendant Response: {response}\n\nPlease provide a fair but humorous decision based on these arguments. Keep your response to 100 words or less. Focus on the argument and response more so than the overview"

  # Set up OpenAI API client, set up the key already in env
  client = openai.OpenAI()

  judy = None
  # Iterate over the list of assistants and find the one named "Judy"
  for assistant in client.beta.assistants.list():
    if assistant.name == "Judy":
      judy = assistant
      print("Judy: ", judy)

  if not judy:
    # Upload a file with an "assistants" purpose
    file = client.files.create(file=open("files/DisorderInTheCourt.pdf", "rb"),
                               purpose='assistants')

    file2 = client.files.create(file=open("files/LawAndDisorder.pdf", "rb"),
                                purpose='assistants')

    # Create an assistant
    judy = client.beta.assistants.create(
        name="Judy",
        instructions=
        "You are a judge inspired by Judge Judy and Larry David. Your role is focussed on finding a fair but humorous resolution to the problem listed. Focus on finding a compromise. Do not add any generic statements about how hard it is to make a judgement or how both sides are right, instead, be sarcastic and funny and deliver a final judgement. Show attitude and do not hold back by being overly polite or too verbose. I have provided you with reference material of absurd court cases that you should feel free to reference in your judgement to add a sense of historical context, be absurd in those references when you can. Keep your judgement to 100 words or less. Use emojis.",
        model="gpt-4-1106-preview",
        tools=[{
            "type": "retrieval"
        }],
        file_ids=[file.id, file2.id])

    print("Judy: ", judy)

  if judy:
    # Create a thread
    thread = client.beta.threads.create()

    # Send the content to the assistant
    message = client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=content,
    )

    # Start processing
    run = client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=judy.id,
    )

    while True:
      run = client.beta.threads.runs.retrieve(thread_id=thread.id,
                                              run_id=run.id)

      if run.status == "completed":
        print("Done!")
        messages = client.beta.threads.messages.list(thread_id=thread.id)

        decision = ""
        for message in messages:
          if message.role == "assistant":
            assert message.content[0].type == "text"
            decision += message.content[0].text.value + "\n"

        case_data = db.get(case_id)
        case_data['decision'] = decision
        case_data['status'] = 'completed'  # Update the status to 'completed'
        db[case_id] = case_data
        break
      else:
        print("Waiting for decision...")
        time.sleep(1)  # Sleep for a short period before checking again


@app.route('/case/<case_id>/judge', methods=['GET'])
def judge_case(case_id):

  thread = Thread(target=process_judgement, args=(case_id, ))
  thread.start()

  return render_template('loading.html', case_id=case_id)


@app.route('/case/<case_id>/view')
def view_judgment(case_id):
  if not db:
    return "Database not found", 500

  case_data = db.get(case_id)
  if not case_data:
    return "Case not found", 404

  full_url = request.url

  # Render a template that displays all the information
  return render_template('judgement.html',
                         case_data=case_data,
                         full_url=full_url)


@app.route('/check_status/<case_id>')
def check_status(case_id):
  # Logic to check the status of the task
  case_data = db.get(case_id)
  print("Checking status!")
  if case_data and case_data.get('status') == 'completed':
    return jsonify({"status": "completed"})
  return jsonify({"status": "pending"})


app.run(host='0.0.0.0', port=5000, debug=True)
