// SniperQuoteTape — NinjaTrader 8 indicator. Writes the chart instrument's
// last price to a small JSON file once a second so the Discord Sniper bridge
// can place its round-number level entry off NinjaTrader's own feed.
//
// INSTALL: this file lives in Documents\NinjaTrader 8\bin\Custom\Indicators\
// (copied there 9/18). NinjaTrader 8 > New > NinjaScript Editor > F5 compiles
// it (or it compiles on the next NinjaTrader start). Then open a 1-minute chart of ES 12-26
// and one of NQ 12-26 (the front month), add the indicator to EACH chart
// (Indicators > SniperQuoteTape) with Folder = the discord-sniper folder.
// Leave those charts open all day. Each chart writes nt_quote_<ROOT>.json:
//   {"root":"ES","instrument":"ES 12-26","last":7702.50,"ts":1789700000.5}
// The bridge treats a file older than 15 seconds as no quote and refuses the
// entry (index_mirror.QUOTE_MAX_AGE_S) — it never guesses a price.

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class SniperQuoteTape : Indicator
    {
        private DateTime lastWrite = DateTime.MinValue;
        private string   path;
        private string   root;

        [NinjaScriptProperty]
        [Display(Name = "Folder", Description = "The discord-sniper folder (where the bridge runs)", Order = 1, GroupName = "Parameters")]
        public string Folder { get; set; }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name        = "SniperQuoteTape";
                Description = "Writes this chart's last price to nt_quote_<ROOT>.json every second for the Discord Sniper bridge.";
                Calculate   = Calculate.OnEachTick;
                IsOverlay   = true;
                Folder      = @"C:\Users\Hulk\Desktop\discord-sniper";
            }
            else if (State == State.DataLoaded)
            {
                root = Instrument.MasterInstrument.Name.ToUpperInvariant();   // "ES", "NQ", "MES" ...
                path = Path.Combine(Folder, "nt_quote_" + root + ".json");
            }
        }

        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if (e.MarketDataType != MarketDataType.Last)
                return;
            if ((DateTime.UtcNow - lastWrite).TotalSeconds < 1.0)
                return;
            Write(e.Price);
        }

        protected override void OnBarUpdate()
        {
            // A quiet minute still refreshes the timestamp, so the bridge knows
            // the feed is alive even when nothing printed.
            if (CurrentBar < 0) return;
            if ((DateTime.UtcNow - lastWrite).TotalSeconds >= 5.0)
                Write(Close[0]);
        }

        private void Write(double last)
        {
            try
            {
                double ts = (DateTime.UtcNow - new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc)).TotalSeconds;
                string json = "{\"root\":\"" + root + "\",\"instrument\":\"" + Instrument.FullName +
                              "\",\"last\":" + last.ToString("0.00", CultureInfo.InvariantCulture) +
                              ",\"ts\":" + ts.ToString("0.0", CultureInfo.InvariantCulture) + "}";
                string tmp = path + ".tmp";
                File.WriteAllText(tmp, json);
                File.Copy(tmp, path, true);          // whole file or nothing
                lastWrite = DateTime.UtcNow;
            }
            catch (Exception) { /* a locked file is not worth a chart error */ }
        }
    }
}
