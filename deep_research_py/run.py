from dotenv import load_dotenv
import asyncio
import typer
from functools import wraps
from prompt_toolkit import PromptSession
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint

from deep_research_py.deep_research import deep_research, write_final_report
from deep_research_py.feedback import generate_feedback
from deep_research_py.ai.providers import get_ai_client

from deep_research_py.utils import console, set_service, set_model
from deep_research_py.common.token_cunsumption import counter
from deep_research_py.common.logging import log_event
from datetime import datetime

load_dotenv()
app = typer.Typer()
session = PromptSession()


def coro(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))

    return wrapper


async def async_prompt(message: str, default: str = "") -> str:
    """Async wrapper for prompt_toolkit."""
    return await session.prompt_async(message)


@app.command()
@coro
async def main(
    concurrency: int = typer.Option(
        default=2, help="Number of concurrent tasks, depending on your API rate limits."
    ),
    service: str = typer.Option(
        default="deepseek",
        help="Which service to use? [openai|deepseek]",
    ),
    model: str = typer.Option(default="ep-20250208165153-wn9ft", help="Which model to use?"), #ep-20250208165153-wn9ft
    max_followup_questions: int = typer.Option(
        default=5,
        help="Maximum number of follow-up questions to generate.",
    ),
    enable_logging: bool = typer.Option(
        default=True,
        help="Enable logging.",
    ),
    log_path: str = typer.Option(
        default="logs",
        help="Path to save the logs.",
    ),
    log_to_stdout: bool = typer.Option(
        default=False,
        help="Log to stdout.",
    ),
):  

    # 根据模型设置service
    if model.startswith("ep-") or model.startswith("deepseek"):
        service = "deepseek"
    else:
        service = "openai"
    set_service(service)
    set_model(model)

    """Initialize the Logger"""
    if enable_logging:
        from deep_research_py.common.logging import initial_logger

        initial_logger(logging_path=log_path, enable_stdout=log_to_stdout)
        console.print(f"[dim]Logging enabled. Logs will be saved to {log_path}[/dim]")

    """Deep Research CLI"""
    console.print(
        Panel.fit(
            "[bold blue]Deep Research Assistant[/bold blue]\n"
            "[dim]An AI-powered research tool[/dim]"
        )
    )

    console.print(f"🛠️ Using [bold green]{service.upper()}[/bold green] service.")

    client = get_ai_client()
    start_time = datetime.now()

    # Get initial inputs with clear formatting
    query = await async_prompt("\n🔍 What would you like to research? ")
    console.print()
    log_event(f"🔍 What would you like to research?: {query}")

    breadth_prompt = "📊 Research breadth (recommended 2-10) [4]: "
    breadth = int((await async_prompt(breadth_prompt)) or "4")
    console.print()
    log_event(f"📊 Research breadth (recommended 2-10) [4]: {breadth}")

    depth_prompt = "🔍 Research depth (recommended 1-5) [2]: "
    depth = int((await async_prompt(depth_prompt)) or "2")
    console.print()
    log_event(f"🔍 Research depth (recommended 1-5) [2]: {depth}")


    # First show progress for research plan
    console.print("\n[yellow]Creating research plan...[/yellow]")
    log_event("\n[yellow]Creating research plan...[/yellow]")
    follow_up_questions = await generate_feedback(
        query, client, model, max_followup_questions
    )

    if len(follow_up_questions) != 0:
        # Then collect answers separately from progress display
        console.print("\n[bold yellow]Follow-up Questions:[/bold yellow]")
        log_event("\n[bold yellow]Follow-up Questions:[/bold yellow]")
        answers = []
        for i, question in enumerate(follow_up_questions, 1):
            console.print(f"\n[bold blue]Q{i}:[/bold blue] {question}")
            log_event(f"\n[bold blue]Q{i}:[/bold blue] {question}")
            answer = await async_prompt("➤ Your answer: ")
            answers.append(answer)
            console.print()
            log_event(f"➤ Your answer: {answer}")

    else:
        console.print("\n[bold green]No follow-up questions needed![/bold green]")
        log_event("\n[bold green]No follow-up questions needed![/bold green]")
        answers = []

    # Combine information
    combined_query = f"""
    Initial Query: {query}
    Follow-up Questions and Answers:
    {chr(10).join(f"Q: {q} A: {a}" for q, a in zip(follow_up_questions, answers))}
    """

    # Now use Progress for the research phase
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # Do research
        task = progress.add_task(
            "[yellow]Researching your topic...[/yellow]", total=None
        )
        research_results = await deep_research(
            query=combined_query,
            breadth=breadth,
            depth=depth,
            concurrency=concurrency,
            client=client,
            model=model,
        )
        progress.remove_task(task)

        # Show learnings
        console.print("\n[yellow]Learnings:[/yellow]")
        log_event("\n[yellow]Learnings:[/yellow]")
        for learning in research_results["learnings"]:
            rprint(f"• {learning}")
            log_event(f"• {learning}")


        # Generate report
        task = progress.add_task("Writing final report...", total=None)
        report = await write_final_report(
            prompt=combined_query,
            learnings=research_results["learnings"],
            visited_urls=research_results["visited_urls"],
            client=client,
            model=model,
        )
        progress.remove_task(task)

        # Show results
        console.print("\n[bold green]Research Complete![/bold green]")
        console.print("\n[yellow]Final Report:[/yellow]")
        console.print(Panel(report, title="Research Report"))
        log_event("\n[bold green]Research Complete![/bold green]")
        log_event("\n[yellow]Final Report:[/yellow]")


        # Show sources
        console.print("\n[yellow]Sources:[/yellow]")
        for url in research_results["visited_urls"]:
            rprint(f"• {url}")

        end_time = datetime.now()
        print(f"Total time: {end_time - start_time}")
        log_event(f"Total time: {end_time - start_time}")

        # Save report
        with open(f"output/{query}_{start_time.strftime('%Y%m%d%H%M%S')}.md", "w") as f:
            f.write(report)

        if enable_logging:
            log_event(
                (
                    f"\nReport has been saved to output.md"
                    f"\nToken usage:"
                    f"Total Input Tokens: {counter.total_input_tokens} "
                    f"Total Output Tokens: {counter.total_output_tokens} "
                    f"Total Reasoning Tokens: {counter.total_reasoning_tokens} "
                    "\nToken usage details:\n"
                    f"{counter}"
                )
            )


def run():
    """Synchronous entry point for the CLI tool."""
    asyncio.run(app())


if __name__ == "__main__":
    asyncio.run(app())
