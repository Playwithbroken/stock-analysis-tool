"""
Report Generator Module
Generates formatted analysis reports using Rich library.
"""

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns
from rich import box
from typing import Dict, Any
from datetime import datetime

from .analyzer import Rating, Valuation, AnalysisResult


class ReportGenerator:
    """Generates formatted stock analysis reports."""
    
    def __init__(self):
        self.console = Console()
    
    def _rating_to_color(self, rating: Rating) -> str:
        """Convert rating to color."""
        colors = {
            Rating.VERY_POSITIVE: "bright_green",
            Rating.POSITIVE: "green",
            Rating.NEUTRAL: "yellow",
            Rating.NEGATIVE: "red",
            Rating.VERY_NEGATIVE: "bright_red",
        }
        return colors.get(rating, "white")
    
    def _rating_to_symbol(self, rating: Rating) -> str:
        """Convert rating to symbol."""
        symbols = {
            Rating.VERY_POSITIVE: "++",
            Rating.POSITIVE: "+",
            Rating.NEUTRAL: "~",
            Rating.NEGATIVE: "-",
            Rating.VERY_NEGATIVE: "--",
        }
        return symbols.get(rating, "?")
    
    def _format_number(self, value: Any, prefix: str = "", suffix: str = "") -> str:
        """Format number for display."""
        if value is None:
            return "N/A"
        if isinstance(value, (int, float)):
            if abs(value) >= 1e12:
                return f"{prefix}{value/1e12:.2f}T{suffix}"
            elif abs(value) >= 1e9:
                return f"{prefix}{value/1e9:.2f}B{suffix}"
            elif abs(value) >= 1e6:
                return f"{prefix}{value/1e6:.2f}M{suffix}"
            elif abs(value) >= 1e3:
                return f"{prefix}{value/1e3:.2f}K{suffix}"
            else:
                return f"{prefix}{value:.2f}{suffix}"
        return str(value)
    
    def print_header(self, data: Dict[str, Any]):
        """Print report header with company info."""
        ticker = data.get("ticker", "UNKNOWN")
        name = data.get("company_name", ticker)
        fund = data.get("fundamentals", {})
        price_data = data.get("price_data", {})
        
        sector = fund.get("sector", "N/A")
        industry = fund.get("industry", "N/A")
        country = fund.get("country", "N/A")
        
        current_price = price_data.get("current_price")
        currency = price_data.get("currency", "USD")
        change_1d = price_data.get("change_1w", 0) / 5 if price_data.get("change_1w") else 0  # Approximate
        
        # Header panel
        header_text = Text()
        header_text.append(f"  {name} ", style="bold white on blue")
        header_text.append(f" ({ticker}) ", style="bold cyan")
        
        self.console.print()
        self.console.print(Panel(header_text, title="Stock Analysis Report", border_style="blue"))
        
        # Quick info
        info_table = Table(show_header=False, box=None, padding=(0, 2))
        info_table.add_column()
        info_table.add_column()
        info_table.add_column()
        info_table.add_column()
        
        price_str = f"{current_price:.2f} {currency}" if current_price else "N/A"
        
        info_table.add_row(
            f"[bold]Price:[/bold] {price_str}",
            f"[bold]Sector:[/bold] {sector}",
            f"[bold]Industry:[/bold] {industry}",
            f"[bold]Country:[/bold] {country}"
        )
        
        self.console.print(info_table)
        self.console.print()
    
    def print_price_performance(self, analysis: AnalysisResult, data: Dict[str, Any]):
        """Print price performance section."""
        self.console.print(Panel("[bold]PRICE PERFORMANCE[/bold]", style="cyan", box=box.SIMPLE))
        
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        table.add_column("Assessment")
        
        for finding in analysis.findings:
            if "error" in finding:
                continue
            metric = finding.get("metric", "")
            value = finding.get("value", "N/A")
            rating = finding.get("rating", Rating.NEUTRAL)
            interp = finding.get("interpretation", "")
            
            color = self._rating_to_color(rating)
            symbol = self._rating_to_symbol(rating)
            
            table.add_row(
                metric,
                f"[{color}]{value}[/{color}]",
                f"[{color}]{symbol}[/{color}] {interp}" if interp else f"[{color}]{symbol}[/{color}]"
            )
        
        self.console.print(table)
        self.console.print(f"[italic]{analysis.summary}[/italic]")
        self.console.print()
    
    def print_volatility(self, analysis: AnalysisResult):
        """Print volatility section."""
        self.console.print(Panel("[bold]VOLATILITY & TRADING[/bold]", style="cyan", box=box.SIMPLE))
        
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        table.add_column("Interpretation")
        
        for finding in analysis.findings:
            if "error" in finding:
                continue
            metric = finding.get("metric", "")
            value = finding.get("value", "N/A")
            rating = finding.get("rating", Rating.NEUTRAL)
            interp = finding.get("interpretation", "")
            
            color = self._rating_to_color(rating)
            
            table.add_row(metric, f"[{color}]{value}[/{color}]", interp)
        
        self.console.print(table)
        self.console.print(f"[italic]{analysis.summary}[/italic]")
        self.console.print()
    
    def print_fundamentals(self, analysis: AnalysisResult):
        """Print fundamental analysis section."""
        self.console.print(Panel("[bold]FUNDAMENTAL ANALYSIS[/bold]", style="cyan", box=box.SIMPLE))
        
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold")
        table.add_column("Metric", style="cyan", width=20)
        table.add_column("Value", justify="right", width=15)
        table.add_column("Signal", width=5, justify="center")
        table.add_column("Interpretation", width=45)
        
        for finding in analysis.findings:
            if "error" in finding:
                continue
            metric = finding.get("metric", "")
            value = finding.get("value", "N/A")
            rating = finding.get("rating", Rating.NEUTRAL)
            interp = finding.get("interpretation", "")
            
            color = self._rating_to_color(rating)
            symbol = self._rating_to_symbol(rating)
            
            table.add_row(
                metric,
                value,
                f"[{color}]{symbol}[/{color}]",
                interp
            )
        
        self.console.print(table)
        self.console.print(f"\n[bold]Summary:[/bold] {analysis.summary}")
        self.console.print(f"[dim]Fundamental Score: {analysis.score:.1f}/100[/dim]")
        self.console.print()
    
    def print_fear_factors(self, analysis: AnalysisResult):
        """Print fear factors / risks section."""
        self.console.print(Panel("[bold red]FEAR FACTORS & RISKS[/bold red]", style="red", box=box.SIMPLE))
        
        if not analysis.findings:
            self.console.print("[green]No significant risk factors identified.[/green]")
            self.console.print()
            return
        
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold red")
        table.add_column("Risk", style="red")
        table.add_column("Details", justify="right")
        table.add_column("Category")
        table.add_column("Impact")
        
        for finding in analysis.findings:
            if "error" in finding:
                continue
            metric = finding.get("metric", "")
            value = finding.get("value", "")
            rating = finding.get("rating", Rating.NEUTRAL)
            interp = finding.get("interpretation", "")
            category = finding.get("category", "General")
            
            color = self._rating_to_color(rating)
            
            table.add_row(
                f"[{color}]{metric}[/{color}]",
                value,
                category,
                interp
            )
        
        self.console.print(table)
        self.console.print(f"\n[bold]{analysis.summary}[/bold]")
        self.console.print()
    
    def print_opportunities(self, analysis: AnalysisResult):
        """Print opportunities section."""
        self.console.print(Panel("[bold green]OPPORTUNITIES & CATALYSTS[/bold green]", style="green", box=box.SIMPLE))
        
        if not analysis.findings:
            self.console.print("[yellow]No clear catalysts identified.[/yellow]")
            self.console.print()
            return
        
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold green")
        table.add_column("Opportunity", style="green")
        table.add_column("Details", justify="right")
        table.add_column("Why It Matters")
        
        for finding in analysis.findings:
            if "error" in finding:
                continue
            metric = finding.get("metric", "")
            value = finding.get("value", "")
            interp = finding.get("interpretation", "")
            
            table.add_row(metric, value, interp)
        
        self.console.print(table)
        self.console.print(f"\n[bold]{analysis.summary}[/bold]")
        self.console.print()
    
    def print_news(self, analysis: AnalysisResult):
        """Print news analysis section."""
        self.console.print(Panel("[bold]RECENT NEWS ANALYSIS[/bold]", style="cyan", box=box.SIMPLE))
        
        if not analysis.findings or (len(analysis.findings) == 1 and "note" in analysis.findings[0]):
            self.console.print("[yellow]No recent news available.[/yellow]")
            self.console.print()
            return
        
        table = Table(box=box.ROUNDED, show_header=True, header_style="bold")
        table.add_column("Date", width=12)
        table.add_column("Source", width=15)
        table.add_column("Headline", width=55)
        table.add_column("Tone", width=10, justify="center")
        
        sentiment_colors = {
            "positive": "green",
            "negative": "red",
            "neutral": "yellow"
        }
        
        for finding in analysis.findings[:10]:
            date = finding.get("date", "")
            source = finding.get("source", "")[:14] if finding.get("source") else ""
            title = finding.get("title", "")
            sentiment = finding.get("sentiment", "neutral")
            
            color = sentiment_colors.get(sentiment, "white")
            
            # Truncate title if too long
            if len(title) > 52:
                title = title[:52] + "..."
            
            table.add_row(
                date[:10] if date else "",
                source,
                title,
                f"[{color}]{sentiment.upper()}[/{color}]"
            )
        
        self.console.print(table)
        self.console.print(f"\n[italic]{analysis.summary}[/italic]")
        self.console.print()
    
    def print_conclusion(self, result: Dict[str, Any], data: Dict[str, Any]):
        """Print final conclusion and recommendation."""
        valuation = result.get("valuation", Valuation.FAIRLY_VALUED)
        total_score = result.get("total_score", 0)
        recommendation = result.get("recommendation", {})
        
        self.console.print(Panel("[bold]CONCLUSION & RECOMMENDATION[/bold]", style="magenta", box=box.DOUBLE))
        
        # Valuation
        val_colors = {
            Valuation.HEAVILY_UNDERVALUED: "bright_green",
            Valuation.UNDERVALUED: "green",
            Valuation.FAIRLY_VALUED: "yellow",
            Valuation.OVERVALUED: "red",
            Valuation.HEAVILY_OVERVALUED: "bright_red",
        }
        val_color = val_colors.get(valuation, "white")
        
        self.console.print(f"[bold]Valuation:[/bold] [{val_color}]{valuation.value}[/{val_color}]")
        self.console.print()
        
        # Score visualization
        score_color = "green" if total_score > 10 else "red" if total_score < -10 else "yellow"
        self.console.print(f"[bold]Overall Score:[/bold] [{score_color}]{total_score:.1f}/100[/{score_color}]")
        
        # Score bar
        normalized = (total_score + 100) / 2  # Convert -100 to 100 -> 0 to 100
        bar_filled = int(normalized / 5)
        bar_empty = 20 - bar_filled
        score_bar = f"[{score_color}]{'█' * bar_filled}[/{score_color}][dim]{'░' * bar_empty}[/dim]"
        self.console.print(f"  {score_bar}")
        self.console.print()
        
        # Recommendations table
        rec_table = Table(box=box.ROUNDED, show_header=True, header_style="bold magenta")
        rec_table.add_column("Investor Type", style="cyan")
        rec_table.add_column("Recommendation")
        
        action = recommendation.get("action", "HOLD")
        action_color = "green" if "BUY" in action else "red" if "SELL" in action or "AVOID" in action else "yellow"
        
        rec_table.add_row("[bold]Action[/bold]", f"[bold {action_color}]{action}[/bold {action_color}]")
        rec_table.add_row("Short-term Traders", recommendation.get("short_term_traders", "N/A"))
        rec_table.add_row("Long-term Investors", recommendation.get("long_term_investors", "N/A"))
        
        self.console.print(rec_table)
        self.console.print()
        
        # Disclaimer
        self.console.print(Panel(
            "[dim italic]This analysis is for informational purposes only and does not constitute "
            "investment advice. Always conduct your own research and consult with a financial "
            "advisor before making investment decisions.[/dim italic]",
            title="Disclaimer",
            border_style="dim"
        ))
    
    def print_comparison(self, data: Dict[str, Any]):
        """Print market comparison section."""
        comparison = data.get("comparison", {})
        
        if "error" in comparison:
            return
        
        self.console.print(Panel("[bold]MARKET COMPARISON (1 Year)[/bold]", style="cyan", box=box.SIMPLE))
        
        stock_return = comparison.get("stock_return_1y", 0)
        index_return = comparison.get("index_return_1y", 0)
        relative = comparison.get("relative_performance", 0)
        index_name = comparison.get("index_name", "S&P 500")
        
        stock_color = "green" if stock_return > 0 else "red"
        index_color = "green" if index_return > 0 else "red"
        rel_color = "green" if relative > 0 else "red"
        
        table = Table(box=box.SIMPLE, show_header=False)
        table.add_column(width=25)
        table.add_column(width=15, justify="right")
        
        table.add_row("Stock Return (1Y)", f"[{stock_color}]{stock_return:+.2f}%[/{stock_color}]")
        table.add_row(f"{index_name} Return (1Y)", f"[{index_color}]{index_return:+.2f}%[/{index_color}]")
        table.add_row("[bold]Relative Performance[/bold]", f"[bold {rel_color}]{relative:+.2f}%[/bold {rel_color}]")
        
        self.console.print(table)
        
        if relative > 0:
            self.console.print(f"[green]Outperforming the market by {relative:.1f} percentage points[/green]")
        else:
            self.console.print(f"[red]Underperforming the market by {abs(relative):.1f} percentage points[/red]")
        
        self.console.print()
    
    def generate_full_report(self, data: Dict[str, Any], analysis_result: Dict[str, Any]):
        """Generate the complete analysis report."""
        analyses = analysis_result.get("analyses", {})
        
        # Clear screen and print header
        self.console.print("\n" + "=" * 80)
        self.print_header(data)
        
        # Price Performance
        self.print_price_performance(
            analyses.get("price_performance"),
            data
        )
        
        # Market Comparison
        self.print_comparison(data)
        
        # Volatility
        self.print_volatility(analyses.get("volatility"))
        
        # Fundamentals
        self.print_fundamentals(analyses.get("fundamentals"))
        
        # Fear Factors
        self.print_fear_factors(analyses.get("fear_factors"))
        
        # Opportunities
        self.print_opportunities(analyses.get("opportunities"))
        
        # News
        self.print_news(analyses.get("news"))
        
        # Conclusion
        self.print_conclusion(analysis_result, data)
        
        self.console.print("=" * 80 + "\n")
        self.console.print(f"[dim]Report generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]")
