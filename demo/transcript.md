# Demo transcript: demo

## 00:00  Architecture

This is a DevOps on-call assistant built with Google's Agent Development Kit and Gemini on Vertex AI. It answers operational questions from our runbooks using retrieval-augmented generation, and it can act: opening incident tickets in Firestore and checking service health. It runs on Cloud Run as a dedicated service account with no keys, and everything is provisioned with Terraform.

## 00:23  Security posture

First, the security posture. The Cloud Run service is not public: an unauthenticated request gets a 403, and the IAM policy has no all-users binding. The runtime identity is a dedicated service account with just two project roles, Vertex AI user and Datastore user, plus read-only access on the runbooks bucket. There are no service account keys anywhere. Locally I reach the service through gcloud run services proxy, which injects my own identity token.

## 00:53  RAG question

Now the agent itself, in the ADK web UI served by Cloud Run. I ask how to recover CouchDB after a crash. The agent calls search runbooks, which embeds the question with Vertex AI and runs a cosine similarity search over the runbook chunks. It then reads the best-matching runbook in full and answers with the exact ordered steps, citing the source file. It is instructed to answer only from the runbooks, so it will say so when something is not covered rather than guess.

## 01:26  Tool trace

The left panel shows the event and trace view: the model's function call to search runbooks, the tool result, the read runbook call, and the final response. This is the same observability you get from ADK locally, now running against the deployed service.

## 01:43  Create a ticket

Next, an action. I ask the agent to open a P1 ticket for this incident. Gemini fills the tool arguments from the conversation, a title, the severity, and a summary, and calls create incident ticket, which writes a document to Firestore using the service account, with no credentials in the code. The agent confirms the ticket id.

## 02:06  Status and ticket list

The agent can chain tools in one turn. Here it checks the queue processor through the status tool, and then lists the open tickets from Firestore, newest first, using a composite index that Terraform created alongside the database.

## 02:21  Open Firestore

Let's verify that write in the Firestore console.

## 02:30  Firestore console

The tickets collection shows the new document with the fields the agent wrote: title, severity, summary, status and a server timestamp.

## 02:40  Open Cloud Run

And finally the Cloud Run service itself, on its security tab.

## 02:46  Cloud Run security

It confirms what we saw on the command line: authentication is required, and the service identity is the dedicated sa ops agent service account. No keys were created for it.

## 02:57  Wrap-up

Everything you saw is defined in Terraform: APIs, the service account and its roles, the private bucket with the runbooks, Firestore and its index, Artifact Registry and the Cloud Run service. The image is built by Cloud Build with its own least-privilege build account. The code, Terraform and this recording are in the GitHub repository linked in the description. Thanks for watching.
