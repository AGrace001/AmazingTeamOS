# TheAmazingTeamOs, The Amazing Team
Free forever. Unlimited members, unlimited offices, no payments.

## Put it live on Render (free)
1. Create a free account at github.com and sign in.
2. Click the + at the top right, then New repository. Name it: theamazingteamos. Click Create repository.
3. Click "uploading an existing file", then drag in EVERYTHING from this folder
   (app.py, config.json, Procfile, render.yaml, README.md, and the whole static folder).
   Click the green Commit changes button.
4. Create a free account at render.com using "Sign in with GitHub".
5. Click New, then Web Service. Choose the theamazingteamos repository.
6. It will read render.yaml by itself. Click Create Web Service and wait about 2 minutes.
7. Your live link appears at the top, like https://theamazingteamos.onrender.com
   That link works day and night, for everybody.

## Logins after it is live
- Member demo: demo@example.com / demo1234
- Admin Backend: add /admin.html to your link. First admin login is
  admin@example.com / admin1234. Change that password at once inside
  Admins and security. Better: on Render, open your service, then
  Environment, and set ADMIN_EMAIL and ADMIN_PASSWORD to your own
  private values before the first deploy, then the demo one never exists.

## Two honest notes
- The free Render service sleeps when nobody uses it for a while.
  The first visit after sleep takes about a minute to wake. Later visits are fast.
- Keep a backup: inside the Admin Backend, System and backup,
  Download full backup, once in a while. When your team grows,
  the small paid Render plan keeps your data disk permanent.
