# TheAmazingTeamOs Launch Guide
## How people access and start using the app

The app is already complete. Nothing inside it is waiting for an API.
Attendance, prospects, earnings, roles, team structure, photos, training,
goals, funds and the Admin Backend all work by themselves.

To let people use it, only ONE thing is truly required: put it on a host.

## Step 1 (required): Hosting, your live link
Platform: Render (render.com), free plan to start.
- Store the code free at GitHub (github.com).
- Connect the GitHub folder to Render, Web Service.
- Render gives a live link like https://theamazingteamos.onrender.com
- Members open the link, no download needed.
- On phone: browser menu, Add to Home Screen. It installs like an app.
- Free plan sleeps when idle. First visit takes about a minute to wake.
- Small paid plan later removes sleep and keeps the data disk permanent.

## Step 2 (optional but nice): Your own domain name
Platform: Cloudflare Registrar or Namecheap (about $10 to $15 a year).
- Buy a name like theamazingteam.app or your own choice.
- In Render: Settings, Custom Domain, add the name.
- Render gives you one line to paste where you bought the name.
- HTTPS security padlock is free and automatic.

## Step 3: How people join, once the link is live
1. You share the live link, or print the office QR code from Settings.
2. The office creator taps Create office. They become Super Admin.
3. Members tap Join office and type the office address or invite code.
4. Super Admin approves them under Members, Pending, if approval is on.
5. Super Admin gives roles with Assign roles (Tutor, Training Head,
   Earnings Manager, Team Leader, Treasurer, Admin) as the team needs.
6. Each person adds their picture and sponsor under My Profile.
That is all. Nobody needs an app store, and nobody pays anything.

## Integrations: needed, later, and only if you want them
REQUIRED: none beyond hosting. The core app is self contained.

LATER, when the team grows:
- Database upgrade: SQLite file today is fine for one office getting
  started. For many offices and permanent data, move to PostgreSQL
  (Neon or Supabase free tiers). This is a code upgrade, ask in chat.
- Backups: download from Admin Backend, System and backup. Keep a copy
  in your Google Drive. Paid hosting disk makes this safer.

ONLY IF YOU WANT THEM:
- Email (password reset mails, invites, approvals):
  Resend or Brevo free tier. Needs a free account and one API key,
  pasted by you into Render, Environment. Never share your password.
- WhatsApp messages: normal wa.me chat links already work free.
  Automatic broadcasts need the WhatsApp Business API from Meta,
  which needs business verification. Optional, not needed to launch.
- SMS reminders or one time codes: Termii (Nigeria) or Twilio.
  Needs an account and small credit. Optional.
- Online dues payment: Paystack or Flutterwave (Nigeria).
  Only if you ever want members to pay dues inside the app.
  The app itself stays free forever either way.
- Photo storage at large scale: Cloudinary free tier.
  Only needed when thousands of pictures are uploaded.
- UptimeRobot (free): pings your link every 5 minutes so the free
  host wakes faster and tells you if the site ever goes down.

## Who does what
- Only you can: create the GitHub, Render, domain and API accounts.
  These need your email, your identity and sometimes your card.
  Never give those passwords to anybody, including in this chat.
- I do: prepare the code, the settings files, and the step by step
  guidance for every click. If you choose an integration, I write the
  code to use it, and you paste the secret key into Render yourself
  under Environment, where only you can see it.

## Recommended order
1. Live link on Render free. People start using it.
2. Your own domain name, when ready.
3. UptimeRobot free, 5 minutes, link wakes faster.
4. Email integration, when members start forgetting passwords.
5. Paid hosting and database upgrade, when the team is big and busy.
