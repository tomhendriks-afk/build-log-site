---
title: How I Built a Production AI System Without Writing the Code
slug: how-i-built-a-production-ai-system-without-writing-the-code
date: 2026-05-01
tag: Architecture
tags: architecture, inaugural, decisions, claude, claude-cowork, gemini, agentic-ai, google-cloud, agents
pinned: true
excerpt: I'm not an engineer, but over the last several weeks I built a production AI system in my spare time, with Claude Cowork as my code assistant. This is the story of how it came to be, and why I didn't start by sketching an architecture diagram.
---

I'm not an engineer. I've never been one. I have always, however, had an affinity with technology, the kind of person who'll happily spend a Sunday afternoon figuring out why the home network is slow, or setting up smart lights that no one else in the house asked for (or ever uses).

Over the last several weeks, in the little bits of spare time I have outside of work and family, I built a production AI system. Every weekday morning it researches the latest AI news, writes a newsletter, narrates a podcast with two hosts, and publishes both to this website before I've finished my morning tea.

I didn't start out planning to run this entire setup. I actually started because I wanted to see how much I could do with the tooling we have available today. I wanted to tinker, learn and experiment. The system is the by-product of me trying and learning as I went. The experience I am picking up along the way is the actual asset, and it's allowing me to do things I could never have imagined a year ago.

I didn't start by sketching an architecture diagram. I didn't start on Google Cloud with a fully automated pipeline. It all started with Claude Cowork.

## Where it started

I was looking for a way to receive a daily newsletter with those stories that would help me stay on top of the latest AI news. Claude has a feature called *scheduled tasks*. So I asked it to run a prompt on a schedule. I set one up: every weekday morning, research the latest AI news from a list of newsletters and websites I'd named, and write me a briefing. This sort of worked, but left a lot to be desired.

The writing was decent. The schedule, less so. Some mornings the task fired and the output landed somewhere useful. Other mornings the schedule slipped. Sometimes the response was just a chat reply that lived in my Claude history and went nowhere: no email, no website, no podcast. It was a prompt with a timer. Not a system that I could rely on.

As I got more into it, I wanted reliability. Consistency. No fails on those mornings where I'd want to listen to the podcast or read the newsletter during my commute. I wasn't trying to ship a product. I just wanted the thing to actually run, every weekday, consistently and fully automated, for me to enjoy it.

## The pattern

The pattern that would repeat for the next several weeks: quite often the system would throw an error, the task failed, timed out, etc, ask Claude how to get past it, try the smallest thing that might work. If it held, keep it. If it didn't, ask the next question.

A lot of this happened in the terminal, and that itself is part of the journey. I used to log into GitHub through the website, upload a file, watch it overwrite the previous one, and assume there had to be a better way. There was. Claude Cowork (the desktop tool I use as my code assistant) walked me through git, the command line, package managers, the whole works. Installing things along the way. What I'd loosely have called *plugins* are, in this world, usually called CLI tools or packages, installed through a package manager like Homebrew. Today, ninety-nine percent of my work on this system happens in two windows: a terminal, and Claude Cowork on the side, watching what I'm doing and answering my questions in real time.

The terminal isn't where I expected to end up. It's also not where I'd recommend most people start. But the way I got there is the same way the rest of the system got built: one blocker, one question, a small iteration, an improvement, and on to the next experiment; one at a time.

I never sat down and designed the architecture. The architecture grew as the questions stacked on top of each other.

## The graduations

Each piece of the system arrived as the answer to a problem. Six of them, in roughly the order they showed up:

1. **"I need this to run reliably."** Claude scheduled tasks couldn't give me that. I asked what would. With Claude's help I landed on **Cloud Run** and **Cloud Scheduler**. Cloud Run is a Google service that runs a small piece of code (in my case, a Python web app) when something asks it to, and scales to zero when nothing is happening. Meaning I pay nothing when it's idle. Cloud Scheduler does what the name says: fire an HTTPS request at a specific time, hit my Cloud Run service, and the work happens. That gave me the reliable trigger Claude scheduled tasks couldn't.
2. **"I need it to remember what it did yesterday."** When the pipeline retries, I don't want it to send the newsletter twice. I asked how to make the system idempotent (meaning it's safe to run multiple times without doing the same thing twice). We landed on **Firestore**, Google's serverless document database. Two collections, no migrations, no joins. One small document per day says "did I send today's newsletter yet?" If the answer is yes, the pipeline skips and exits. The whole state model is two documents wide.
3. **"I need to actually call Claude from my code."** Worth its own section, see below. I had to move away from 'manual' Claude.
4. **"I need to send the newsletter as a real email."** I didn't want to spin up an SMTP server. I asked for the simplest path. We landed on the **Gmail API** with OAuth. The pipeline drafts the newsletter inside my own Gmail account and then sends it from there. As a side effect, I had a place to review the draft before it went out. That review window became the human-in-the-loop gate, until I trained myself out of it.
5. **"I want to turn the transcript into a podcast."** This one had a clear answer: **ElevenLabs**, a text-to-speech service that's good enough to be mistaken for a real podcast. The transcript gets parsed into speaker segments, each segment gets narrated in one of two voices, the chunks get stitched into a single MP3, and the MP3 lands in **Google Cloud Storage** with a public URL.
6. **"I want a website for all of this."** We landed on **Cloudflare Pages**, a static site host, fed by **GitHub** repos. The pipeline writes new newsletter HTML and a new podcast feed straight into a GitHub repository through GitHub's Contents API. Cloudflare watches the repo and rebuilds the site within a minute. Three sister sites (briefing, podcast, take) all run this way. This site, the build log, makes four.

For the visuals on those sites (diagrams, banner images, podcast thumbnails, that sort of thing) I lean on **Gemini**. Right now Gemini's multimodal generation is meaningfully better than Claude's for image work, but that gap is closing, but for now I use Claude Cowork for code and reasoning, Gemini for pixels.

## The Claude component, up close

A bit more context on the piece that does the actual work each morning.

In this system, Claude shows up as a series of **API calls**: straight HTTPS requests from my Cloud Run service to the Anthropic API, authenticated with an API key that lives in Google's Secret Manager (not in the code, not in environment variables, not anywhere it could leak by accident). The pipeline makes four Claude calls back to back, each with a different job.

1. **Research**, using **Claude Sonnet** with the `web_search` tool turned on. It gets a prompt that says: here are the angles I care about, here are the AI newsletters I subscribe to that you should pull from my Gmail for context, here are the named thought leaders I want to track, and here's the open web. Find me ten to fifteen stories worth covering.
2. **Writing**, using **Claude Opus 4.6**. It takes the research brief, plus a "golden copy" example of a newsletter I think hits the mark, and writes the actual newsletter in markdown.
3. **Self-review**, also **Claude Opus 4.6**. Same model is asked to grade its own output across hook, depth, thought leadership, and resources. If the score dips below a threshold, it rewrites with the specific feedback in mind.
4. **Podcast transcript**, also **Claude Opus 4.6**. It's a full two-host conversation, around two thousand to twenty-five hundred words (usually translates to just under 10 minutes of audio).

A note on the prompts themselves: I didn't write any of them in one sitting. They've evolved over weeks of "the output was off in this way, how do I fix it?" Claude helped me iterate on the prompts that drive Claude.

One more thing I learned the hard way. Claude Cowork has a useful blind spot: it sometimes forgets how *this particular* system works and reverts to suggesting setups it's seen elsewhere. For a stretch I kept getting nudged toward Vercel for hosting, even though I'd already picked Cloudflare Pages and was happily working with it. The fix turned out to be a small thing called a **skill**: essentially a piece of context I can create and then load on demand that says "here's how my system actually works." I built one called *"ambient advantage architecture"* and now I invoke it every time I ask Claude to provide me commands for a terminal session for this project. The drift went away. That moment, building a tool to keep my AI coworker focused and consistent, felt like a milestone of its own.

## Where I ended up

This is the picture I couldn't have drawn in week one. It's the end result of all the questions I asked.

[Architecture diagram, coming soon, generated with Gemini]

Cloud Scheduler fires a request at my Cloud Run service every weekday morning. Cloud Run talks to Anthropic for the writing, Gmail for the email, ElevenLabs for the audio. State lives in Firestore. The MP3 lands in Cloud Storage. The newsletter and the podcast feed are written to GitHub, and Cloudflare Pages rebuilds the public sites within a minute. Each box on that diagram is its own little story, and the rest of this build log will fill in the boxes one by one.

## How I trained myself out of the loop

The thing I'm most content with is something the system *doesn't* do anymore.

In the early versions I put myself in the loop. The pipeline would draft the newsletter, draft the transcript, drop them in my Gmail, and wait for me to apply an "approved" label. I'd read, sometimes edit, then click. That was fine for a few weeks. But it meant that I had to do this review in the morning every day, or no content gets created. I also realized that the quality of the content generation is such that I did not need to be in the loop for this system to run.

So I built an improved flow with better AI. The self-review pass came in. A quality-check module came in. It grades each draft on structure, depth, and a few other dimensions. If everything scores above the threshold, the approval label gets applied automatically, and the pipeline keeps moving. If anything fails, I get an email and I'm back in the loop for that one morning only. I got there by asking Claude (using Cowork) all the time how to make these changes, what it requires, how to do it. If the instructions weren't clear, I'd ask Claude to explain again in plain English, break it down in steps, etc.

Today I don't manually label anything. The system runs from end to end on its own, every weekday morning, and it's right nearly 100% of the time. When it isn't, I hear about it before subscribers do. That's exactly the relationship I want with it.

The takeaway I'd offer: the question isn't whether AI is good enough to run unsupervised. It's whether you've built the workflow that lets it run unsupervised *consistently*. Approval gates are a useful crutch on the way to that workflow. They're not always the destination.

## What this is teaching me

Here's the 3 takeaways that this experience leaves me with:

1. **You can go very far, very fast, by tinkering.** Most of what's in this system came from an evening here, a Saturday morning there. Pick something small that doesn't work, ask the next question, try the smallest possible answer. Repeat. The system you end up with is rarely the one you'd have planned, and that's usually a good thing.
2. **Launch, then iterate.** Every component went live before it was ready. The first newsletter was rough. The first podcast had pacing issues. The first website was ugly. None of it would be where it is now if I'd waited until any of those felt finished. Actually launching the pieces into production and seeing how it performs provides real feedback (even just my own daily reading habit) which surfaces issues that no design session ever will.
3. **Treat Claude Cowork as a real coworker.** Not a search engine, not a code generator. A coworker. Tell it what you're trying to do and why. Show it your terminal output (I did a lot of copy-pasting from terminal to Claude Cowork, and vice versa). Disagree when its suggestion doesn't sit right. Build it the context it needs to be useful. The *skill* I mentioned earlier is a small example. The relationship gets better the more you invest in it, the same way it does with any human teammate.

## What's next

I'm still tinkering with this. The system isn't finished; none of it is. There's a backlog of things I want to improve, larger things I want to add, and the kind of unexpected questions that only show up once you actually run something every day.

This site is where I'll write about some of that. No fixed schedule, no manifesto. When I learn something worth sharing (a gotcha I didn't see coming, a graduation moment, a tool I'd recommend or warn against), I'll post about it here.

If that sounds useful, follow along. If you're somewhere in the middle of your own version of this, I'd love to hear how it's going. Find me on LinkedIn.

I hope my experience will encourage you to become a tinkerer too. It's never been easier to bring your ideas to life.
