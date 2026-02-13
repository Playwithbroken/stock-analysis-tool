#!/usr/bin/env python3
"""
Stock Market Analysis Tool
A comprehensive, data-driven stock analysis system.

Usage:
    python main.py TICKER
    python main.py --help

Example:
    python main.py AAPL
    python main.py MSFT
    python main.py NVDA
"""

import argparse
import sys
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.data_fetcher import DataFetcher
from src.analyzer import StockAnalyzer
from src.report_generator import ReportGenerator


console = Console()


def analyze_stock(ticker: str, verbose: bool = False):
    """Run full analysis on a stock."""
    
    console.print(f"\n[bold cyan]Starting analysis for {ticker.upper()}...[/bold cyan]\n")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        
        # Fetch data
        task = progress.add_task("Fetching market data...", total=None)
        try:
            fetcher = DataFetcher(ticker)
            data = fetcher.get_all_data()
            progress.update(task, description="[green]Data fetched successfully![/green]")
        except Exception as e:
            progress.update(task, description=f"[red]Error fetching data: {e}[/red]")
            console.print(f"\n[red]Failed to fetch data for {ticker}. Please check the ticker symbol.[/red]")
            return None
        
        # Analyze
        progress.update(task, description="Analyzing fundamentals...")
        try:
            analyzer = StockAnalyzer(data)
            result = analyzer.generate_recommendation()
            progress.update(task, description="[green]Analysis complete![/green]")
        except Exception as e:
            progress.update(task, description=f"[red]Error during analysis: {e}[/red]")
            console.print(f"\n[red]Analysis failed: {e}[/red]")
            return None
        
        # Generate report
        progress.update(task, description="Generating report...")
        try:
            report_gen = ReportGenerator()
            progress.update(task, description="[green]Done![/green]")
        except Exception as e:
            console.print(f"\n[red]Report generation failed: {e}[/red]")
            return None
    
    # Print the full report
    report_gen.generate_full_report(data, result)
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Stock Market Analysis Tool - Comprehensive stock analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python main.py AAPL           Analyze Apple Inc.
    python main.py MSFT           Analyze Microsoft
    python main.py TSLA           Analyze Tesla
    python main.py SAP.DE         Analyze SAP (German Exchange)
    python main.py ^GSPC          Analyze S&P 500 Index
    
Supported formats:
    - US Stocks: AAPL, MSFT, GOOGL
    - German Stocks: SAP.DE, BMW.DE
    - ETFs: SPY, QQQ
    - Indices: ^GSPC, ^DJI
        """
    )
    
    parser.add_argument(
        "ticker",
        type=str,
        help="Stock ticker symbol (e.g., AAPL, MSFT, NVDA)"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version="Stock Analysis Tool v1.0.0"
    )
    
    args = parser.parse_args()
    
    if not args.ticker:
        parser.print_help()
        sys.exit(1)
    
    # Run analysis
    result = analyze_stock(args.ticker, args.verbose)
    
    if result is None:
        sys.exit(1)
    
    # Exit with appropriate code based on recommendation
    action = result.get("recommendation", {}).get("action", "HOLD")
    if "SELL" in action or "AVOID" in action:
        sys.exit(2)  # Warning
    
    sys.exit(0)


if __name__ == "__main__":
    main()
