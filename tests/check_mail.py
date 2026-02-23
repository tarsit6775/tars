"""Check Mail.app accounts and try to find the code."""
import subprocess, re, time

# Check what accounts exist in Mail.app
script1 = '''
tell application "Mail"
    set accts to every account
    set out to ""
    repeat with a in accts
        set out to out & name of a & " - " & (email addresses of a as string) & "\\n"
    end repeat
    return out
end tell
'''
r1 = subprocess.run(["osascript", "-e", script1], capture_output=True, text=True, timeout=15)
print("=== MAIL ACCOUNTS ===")
print(r1.stdout)
print(r1.stderr[:500] if r1.stderr else "")

# Try to get ALL recent messages (last 10 minutes)
script2 = '''
tell application "Mail"
    set out to ""
    set allAccounts to every account
    repeat with acct in allAccounts
        try
            set inboxMailbox to mailbox "INBOX" of acct
            set msgs to messages 1 thru 5 of inboxMailbox
            repeat with msg in msgs
                set out to out & "FROM: " & sender of msg & "\\n"
                set out to out & "SUBJ: " & subject of msg & "\\n"
                set out to out & "DATE: " & (date received of msg as string) & "\\n\\n"
            end repeat
        end try
    end repeat
    return out
end tell
'''
r2 = subprocess.run(["osascript", "-e", script2], capture_output=True, text=True, timeout=30)
print("=== RECENT MESSAGES ===")
print(r2.stdout[:2000])
print(r2.stderr[:500] if r2.stderr else "")
