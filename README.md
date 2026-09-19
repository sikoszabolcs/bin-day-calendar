# binday-calendar

Turns the Wiltshire Council waste collection calendar for one property into:

- `bins.ics` - a calendar you can subscribe to on your phone (rebuilt monthly, committed only when the dates change)
- an email with the schedule line for the bin day device, once a year when the council publishes the new calendar (optional)

## Set up (once)

1. Create a **public** GitHub repository and push these files. Public is needed so the phone can fetch `bins.ics` without a login.
2. Settings > Secrets and variables > Actions > New repository secret:
   - `UPRN` - your property's UPRN (from the council calendar link, or findmyaddress.co.uk)
   - Optional, for the device email: `EMAIL_TO`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`
3. Actions tab > "bins ics" > Run workflow. It fetches the PDF and commits `bins.ics`.
4. Check the file in the repo: one all-day event per collection day, September to August.

## Subscribe on iPhone

Settings > Calendar > Accounts > Add Account > Other > Add Subscribed Calendar, and paste:

    https://raw.githubusercontent.com/<user>/<repo>/main/bins.ics

Tap Next, then Save. In the subscription's settings turn off "Remove Alarms" to keep the 18:00 evening-before reminders. iOS refreshes subscribed calendars on its own; the workflow rebuilds the file on the 1st of each month, so the new September calendar shows up without you doing anything.

Android: Google Calendar on the web > Other calendars > + > From URL, same address.

## Run locally

    pip install -r requirements.txt
    python bins_ics.py --uprn <UPRN> -o bins.ics
    python bins_ics.py --pdf Waste_collection_calendar.pdf -o bins.ics     # from a downloaded PDF
    python binday_calendar.py --uprn <UPRN>                                # print the device line

## When it breaks

If the council changes the PDF layout the workflow fails and GitHub emails you. Download the PDF from the council site and do that year by hand; fix `parse_streams()` in `binday_calendar.py` when you get a chance.
