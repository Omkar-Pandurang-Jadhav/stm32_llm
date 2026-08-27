#include "stm32f103xb.h"
#include <stdint.h>

int main(void)
{
    RCC->APB2ENR |= (1U << 2);
    GPIOA->CRH &= ~(0xFU << 4);
    GPIOA->CRH |= (0xBU << 4);
    GPIOA->CRH &= ~(0xFU << 8);
    GPIOA->CRH |= (0x4U << 8);
    RCC->APB2ENR |= (1U << 14);
    USART1->BRR = 0x45U;
    USART1->CR1 = 0;
    USART1->CR2 = 0U;
    USART1->CR1 |= USART_CR1_TE | USART_CR1_UE;
    uint8_t data = 0x55U;
    while (!( USART1->SR & USART_SR_TXE )) { }
    USART1->DR = data;

    while (1)
    {
    }
}
