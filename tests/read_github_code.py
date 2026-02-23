"""Read GitHub verification code from Mail.app."""
import sys, os, time, subprocess, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use AppleScript to read latest email from GitHub
script = '''
tell application "Mail"
    set allAccounts to every account
    repeat with acct in allAccounts
        set acctName to name of acct
        try
            set inboxMailbox to mailbox "INBOX" of acct
            set msgs to (messages of inboxMailbox whose sender contains "github" and date received > (current date) - 600)
            repeat with msg in msgs
                set subj to subject of msg
                set bod to content of msg
                set sndr to sender of msg
                set dt to date received of msg
                log "---"
                log "FROM: " & sndr
                log "SUBJECT: " & subj
                log "DATE: " & (dt as string)
                log "BODY: " & (text 1 thru 500 of bod)
            end repeat
        end try
    end repeat
end tell
'''

result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=30)
print("STDOUT:", result.stdout)
print("STDERR:", result.stderr[:2000])

# Look for verification code pattern (usually 6-8 digits)
combined = result.stdout + result.stderr
codes = re.findall(r'\b(\d{6,8})\b', combined)
if codes:
    print(f"\nPossible codes: {codes}")
