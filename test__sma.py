from langchain_classic.prompts import PromptTemplate
from langchain_classic.chains import LLMChain
from langchain_classic.chat_models import ChatOpenAI

prompt = PromptTemplate(
    input_variables=["name"],
    template="Hello {name}, comment ça va ?"
)


chat = ChatOpenAI(
    model_name="gpt-3.5-turbo",
    temperature=0.7,
    openai_api_key="ta_clef_openai_ici"  # <-- ici
)

chain = LLMChain(llm=chat, prompt=prompt)
result = chain.run(name="Karizma")
print(result)
