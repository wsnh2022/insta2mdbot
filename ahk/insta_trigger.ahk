#SingleInstance Force
#Requires AutoHotkey v2.0+
~*^s::Reload
Tray := A_TrayMenu, Tray.Delete() Tray.AddStandard() Tray.Add()
Tray.Add("Open Folder", (*)=> Run(A_ScriptDir)) Tray.SetIcon("Open Folder", "shell32.dll",5)
; -----------------

class InstaBot {
    static WorkerUrl      := "https://instatomdnotes-worker.yogiswagger28.workers.dev"
    static AppTitle       := "Insta Bot"

    ; Returns path to passphrase.txt sitting beside this script
    static PassphraseFile() => A_ScriptDir "\passphrase.txt"

    static LoadPassphrase() {
        if !FileExist(InstaBot.PassphraseFile())
            return ""
        return Trim(FileRead(InstaBot.PassphraseFile()))
    }

    static Trigger() {
        A_Clipboard := ""
        Send '^c'
        ClipWait 0.5
        clip := A_Clipboard

        ; Validate clipboard contains an Instagram post URL
        if !InStr(clip, "instagram.com/p/") {
            InstaBot.Toast("Not an Instagram post URL - copy a post link first", 3)
            return
        }

        ; Extract shortcode
        if !RegExMatch(clip, "instagram\.com/p/([A-Za-z0-9_-]+)", &m) {
            InstaBot.Toast("Could not extract shortcode from URL", 3)
            return
        }

        cleanUrl   := "https://www.instagram.com/p/" . m[1] . "/"
        passphrase := InstaBot.LoadPassphrase()

        if (passphrase = "") {
            InstaBot.Toast("passphrase.txt is missing or empty - add it beside the script", 3)
            return
        }

        body := '{"instagram_url":"' . cleanUrl . '"}'

        try {
            whr := ComObject("WinHttp.WinHttpRequest.5.1")
            whr.Open("POST", InstaBot.WorkerUrl, false)   ; false = synchronous
            whr.SetRequestHeader("Content-Type", "application/json")
            whr.SetRequestHeader("X-Access-Key", passphrase)
            whr.Send(body)
            status := whr.Status
        } catch Error as e {
            InstaBot.Toast("HTTP request failed: " . e.Message, 3)
            return
        }

        if (status = 200)
            InstaBot.Toast("Triggered - GitHub Actions is processing the post", 1)
        else if (status = 401)
            InstaBot.Toast("Wrong passphrase - update passphrase.txt", 3)
        else if (status = 429)
            InstaBot.Toast("Rate limited - wait a minute and try again", 2)
        else
            InstaBot.Toast("Unexpected response (HTTP " . status . ")", 3)
    }

    ; Show a tray notification and auto-dismiss after 4 seconds
    ; iconType: 1 = Info, 2 = Warning, 3 = Error
    static Toast(text, iconType := 1) {
        TrayTip text, InstaBot.AppTitle, iconType
        SetTimer(() => TrayTip(), -4000)
    }
}

; --- Hotkeys ---
!i:: InstaBot.Trigger()
